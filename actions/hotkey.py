# actions/hotkey.py — send keyboard shortcuts

import win32api
import win32con
from pynput.keyboard import Controller, Key as PKey

_keyboard = Controller()

# ---------------------------------------------------------------------------
# pynput key map — used by send() for regular tap hotkeys
# ---------------------------------------------------------------------------
SPECIAL_KEYS = {
    "ctrl":   PKey.ctrl,
    "shift":  PKey.shift,
    "alt":    PKey.alt,
    "win":    PKey.cmd,
    "enter":  PKey.enter,
    "space":  PKey.space,
    "tab":    PKey.tab,
    "esc":    PKey.esc,
    "up":     PKey.up,
    "down":   PKey.down,
    "left":   PKey.left,
    "right":  PKey.right,
    "f1":     PKey.f1,  "f2":  PKey.f2,  "f3":  PKey.f3,  "f4":  PKey.f4,
    "f5":     PKey.f5,  "f6":  PKey.f6,  "f7":  PKey.f7,  "f8":  PKey.f8,
    "f9":     PKey.f9,  "f10": PKey.f10, "f11": PKey.f11, "f12": PKey.f12,
    "delete": PKey.delete, "backspace": PKey.backspace, "home": PKey.home,
    "end":    PKey.end, "page_up": PKey.page_up, "page_down": PKey.page_down,
    "media_play_pause": PKey.media_play_pause,
    "media_next":       PKey.media_next,
    "media_previous":   PKey.media_previous,
    "media_volume_up":  PKey.media_volume_up,
    "media_volume_down":PKey.media_volume_down,
    "media_volume_mute":PKey.media_volume_mute,
}

# ---------------------------------------------------------------------------
# Windows virtual-key map — used by press_keys / release_keys.
# win32api.keybd_event updates GetKeyState() system-wide so modifier-aware
# apps (like Resolve) see the key as held when reading mouse scroll events.
# ---------------------------------------------------------------------------
VK_CODES = {
    "ctrl":       0x11,  "shift":     0x10,  "alt":       0x12,
    "win":        0x5B,  "enter":     0x0D,  "esc":       0x1B,
    "space":      0x20,  "tab":       0x09,  "backspace": 0x08,
    "delete":     0x2E,  "home":      0x24,  "end":       0x23,
    "page_up":    0x21,  "page_down": 0x22,
    "up":         0x26,  "down":      0x28,  "left":      0x25,  "right": 0x27,
    "f1":  0x70, "f2":  0x71, "f3":  0x72, "f4":  0x73,
    "f5":  0x74, "f6":  0x75, "f7":  0x76, "f8":  0x77,
    "f9":  0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def _parse_vk_codes(hotkey_str: str) -> list[int]:
    codes = []
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if part in VK_CODES:
            codes.append(VK_CODES[part])
        elif len(part) == 1:
            codes.append(ord(part.upper()))
    return codes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_hotkey(hotkey_str: str):
    """Parse 'ctrl+shift+s' into a list of pynput key objects."""
    parts = [p.strip().lower() for p in hotkey_str.split('+')]
    keys = []
    for p in parts:
        if p in SPECIAL_KEYS:
            keys.append(SPECIAL_KEYS[p])
        elif len(p) == 1:
            keys.append(p)
    return keys


def send(hotkey_str: str):
    """Press and release a hotkey combination — uses pynput (tap)."""
    keys = parse_hotkey(hotkey_str)
    if not keys:
        return
    for k in keys:
        _keyboard.press(k)
    for k in reversed(keys):
        _keyboard.release(k)


def press_keys(hotkey_str: str):
    """Hold keys down via win32api.keybd_event (for hold/toggle actions)."""
    vks = _parse_vk_codes(hotkey_str)
    print(f'[hold] press  {hotkey_str!r}  vks={vks}')
    for vk in vks:
        win32api.keybd_event(vk, 0, 0, 0)


def release_keys(hotkey_str: str):
    """Release held keys via win32api.keybd_event."""
    vks = _parse_vk_codes(hotkey_str)
    print(f'[hold] release {hotkey_str!r}  vks={vks}')
    for vk in reversed(vks):
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
