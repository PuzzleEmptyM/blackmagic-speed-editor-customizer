# hid_layer.py — Editor Device HID abstraction
#
# Authentication algorithm by Sylvain Munaut <tnt@246tNt.com> (Apache-2.0)
# https://github.com/octimot/blackmagic-speededitor

import enum
import struct
import threading
from typing import Callable, List, Optional

import hid

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Key(enum.IntEnum):
    NONE          = 0x00
    SMART_INSRT   = 0x01
    APPND         = 0x02
    RIPL_OWR      = 0x03
    CLOSE_UP      = 0x04
    PLACE_ON_TOP  = 0x05
    SRC_OWR       = 0x06
    IN            = 0x07
    OUT           = 0x08
    TRIM_IN       = 0x09
    TRIM_OUT      = 0x0a
    ROLL          = 0x0b
    SLIP_SRC      = 0x0c
    SLIP_DEST     = 0x0d
    TRANS_DUR     = 0x0e
    CUT           = 0x0f
    DIS           = 0x10
    SMTH_CUT      = 0x11
    SOURCE        = 0x1a
    TIMELINE      = 0x1b
    SHTL          = 0x1c
    JOG           = 0x1d
    SCRL          = 0x1e
    SYNC_BIN      = 0x1f
    ESC           = 0x31
    AUDIO_LEVEL   = 0x2c
    FULL_VIEW     = 0x2d
    TRANS         = 0x22
    SPLIT         = 0x2f
    SNAP          = 0x2e
    RIPL_DEL      = 0x2b
    CAM1          = 0x33
    CAM2          = 0x34
    CAM3          = 0x35
    CAM4          = 0x36
    CAM5          = 0x37
    CAM6          = 0x38
    CAM7          = 0x39
    CAM8          = 0x3a
    CAM9          = 0x3b
    LIVE_OWR      = 0x30
    VIDEO_ONLY    = 0x25
    AUDIO_ONLY    = 0x26
    STOP_PLAY     = 0x3c


class Led(enum.IntFlag):
    CLOSE_UP   = (1 <<  0)
    CUT        = (1 <<  1)
    DIS        = (1 <<  2)
    SMTH_CUT   = (1 <<  3)
    TRANS      = (1 <<  4)
    SNAP       = (1 <<  5)
    CAM7       = (1 <<  6)
    CAM8       = (1 <<  7)
    CAM9       = (1 <<  8)
    LIVE_OWR   = (1 <<  9)
    CAM4       = (1 << 10)
    CAM5       = (1 << 11)
    CAM6       = (1 << 12)
    VIDEO_ONLY = (1 << 13)
    CAM1       = (1 << 14)
    CAM2       = (1 << 15)
    CAM3       = (1 << 16)
    AUDIO_ONLY = (1 << 17)


class JogLed(enum.IntFlag):
    JOG  = (1 << 0)
    SHTL = (1 << 1)
    SCRL = (1 << 2)


class JogMode(enum.IntEnum):
    RELATIVE          = 0
    ABSOLUTE          = 1
    RELATIVE_2        = 2
    ABSOLUTE_DEADZERO = 3


# ---------------------------------------------------------------------------
# Authentication (Sylvain Munaut's reverse-engineered algorithm)
# ---------------------------------------------------------------------------

def _rol8(v):
    return ((v << 56) | (v >> 8)) & 0xffffffffffffffff


def _rol8n(v, n):
    for _ in range(n):
        v = _rol8(v)
    return v


def _bmd_kbd_auth(challenge: int) -> int:
    AUTH_EVEN_TBL = [
        0x3ae1206f97c10bc8, 0x2a9ab32bebf244c6,
        0x20a6f8b8df9adf0a, 0xaf80ece52cfc1719,
        0xec2ee2f7414fd151, 0xb055adfd73344a15,
        0xa63d2e3059001187, 0x751bf623f42e0dde,
    ]
    AUTH_ODD_TBL = [
        0x3e22b34f502e7fde, 0x24656b981875ab1c,
        0xa17f3456df7bf8c3, 0x6df72e1941aef698,
        0x72226f011e66ab94, 0x3831a3c606296b42,
        0xfd7ff81881332c89, 0x61a3f6474ff236c6,
    ]
    MASK = 0xa79a63f585d37bf0

    n = challenge & 7
    v = _rol8n(challenge, n)

    if (v & 1) == ((0x78 >> n) & 1):
        k = AUTH_EVEN_TBL[n]
    else:
        v = v ^ _rol8(v)
        k = AUTH_ODD_TBL[n]

    return v ^ (_rol8(v) & MASK) ^ k


# ---------------------------------------------------------------------------
# SpeedEditor
# ---------------------------------------------------------------------------

class SpeedEditor:
    USB_VID = 0x1edb
    USB_PID = 0xda0e

    def __init__(self):
        self.dev = hid.device()
        self.dev.open(self.USB_VID, self.USB_PID)
        self._reauth_timer: Optional[threading.Timer] = None

        # Callbacks — assign these before calling run()
        self.on_key:     Optional[Callable[[List[Key]], None]] = None
        self.on_jog:     Optional[Callable[[JogMode, int], None]] = None
        self.on_battery: Optional[Callable[[bool, int], None]] = None

    def close(self):
        if self._reauth_timer:
            self._reauth_timer.cancel()
        self.dev.close()
        self.dev = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self):
        # Reset auth state machine
        self.dev.send_feature_report(b'\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        # Get keyboard challenge
        data = self.dev.get_feature_report(6, 10)
        if bytes(data[0:2]) != b'\x06\x00':
            raise RuntimeError(f'Unexpected auth challenge header: {bytes(data).hex()}')
        challenge = int.from_bytes(bytes(data[2:]), 'little')

        # Send our challenge (we don't actually care about authenticating the device)
        self.dev.send_feature_report(b'\x06\x01\x00\x00\x00\x00\x00\x00\x00\x00')

        # Read (and discard) the device's response to our challenge
        data = self.dev.get_feature_report(6, 10)
        if bytes(data[0:2]) != b'\x06\x02':
            raise RuntimeError(f'Unexpected auth response header: {bytes(data).hex()}')

        # Compute and send our response
        response = _bmd_kbd_auth(challenge)
        self.dev.send_feature_report(b'\x06\x03' + response.to_bytes(8, 'little'))

        # Read status / timeout
        data = self.dev.get_feature_report(6, 10)
        if bytes(data[0:2]) != b'\x06\x04':
            raise RuntimeError(f'Unexpected auth status header: {bytes(data).hex()}')

        timeout = int.from_bytes(bytes(data[2:4]), 'little')
        print(f'[auth] Authenticated. Re-auth in {timeout - 10}s.')

        # Schedule re-authentication before timeout
        self._reauth_timer = threading.Timer(timeout - 10, self.authenticate)
        self._reauth_timer.daemon = True
        self._reauth_timer.start()
        return timeout

    # ------------------------------------------------------------------
    # LED control
    # ------------------------------------------------------------------

    def set_leds(self, leds: Led):
        self.dev.write(struct.pack('<BI', 2, int(leds)))

    def set_jog_leds(self, jog_leds: JogLed):
        self.dev.write(struct.pack('<BB', 4, int(jog_leds)))

    def set_jog_mode(self, mode: JogMode):
        self.dev.write(struct.pack('<BBIB', 3, int(mode), 0, 255))

    # ------------------------------------------------------------------
    # Report parsing
    # ------------------------------------------------------------------

    def _handle_03(self, report):
        # Jog wheel: u8 report_id, u8 mode, le32 signed value, u8 unknown
        b = bytes(report)
        _, jm, jv, _ = struct.unpack_from('<BBiB', b)
        if self.on_jog:
            self.on_jog(JogMode(jm), jv)

    def _handle_04(self, report):
        # Key presses: u8 report_id, 6x le16 keycodes (0 = none)
        b = bytes(report)
        keys = [Key(k) for k in struct.unpack_from('<6H', b[1:]) if k != 0]
        if self.on_key:
            self.on_key(keys)

    def _handle_07(self, report):
        # Battery: u8 report_id, u8 charging, u8 level
        b = bytes(report)
        _, charging, level = struct.unpack_from('<BBB', b)
        if self.on_battery:
            self.on_battery(bool(charging), level)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        handlers = {
            0x03: self._handle_03,
            0x04: self._handle_04,
            0x07: self._handle_07,
        }
        while True:
            report = self.dev.read(64, 1000)
            if not report:
                continue
            h = handlers.get(report[0])
            if h:
                h(report)
            else:
                print(f'[unhandled] {bytes(report[:8]).hex()}')
