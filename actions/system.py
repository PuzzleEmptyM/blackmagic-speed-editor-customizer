# actions/system.py — system control (volume, brightness)
#
# Requires:  pip install pycaw screen-brightness-control
# pycaw pulls in comtypes automatically.

VOL_STEP    = 0.02   # 2 % per jog tick
BRIGHT_STEP = 5      # 5 % per jog tick


# ---------------------------------------------------------------------------
# Master volume — uses Windows media keys so the native OSD appears
# ---------------------------------------------------------------------------

VK_VOLUME_UP   = 0xAF
VK_VOLUME_DOWN = 0xAE

def adjust_master_volume(delta: float):
    """Raise or lower master volume one Windows step, showing the native OSD."""
    try:
        import win32api
        import win32con
        vk = VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception as e:
        print(f'[volume] {e}')


# ---------------------------------------------------------------------------
# Per-app volume
# ---------------------------------------------------------------------------

def adjust_app_volume(app_name: str, delta: float):
    """Raise or lower volume for a running app (partial name, case-insensitive)."""
    try:
        from pycaw.pycaw import AudioUtilities
        name_lower = app_name.lower().replace('.exe', '')
        matched = False
        for session in AudioUtilities.GetAllSessions():
            if session.Process:
                proc = session.Process.name().lower().replace('.exe', '')
                if name_lower in proc:
                    vol = session.SimpleAudioVolume
                    vol.SetMasterVolume(max(0.0, min(1.0, vol.GetMasterVolume() + delta)), None)
                    matched = True
        if not matched:
            print(f'[app_volume] No session found matching {app_name!r}')
    except Exception as e:
        print(f'[app_volume] {e}')


def list_audio_apps() -> list[str]:
    """Return names of apps currently producing audio."""
    try:
        from pycaw.pycaw import AudioUtilities
        names = []
        for session in AudioUtilities.GetAllSessions():
            if session.Process:
                names.append(session.Process.name().replace('.exe', ''))
        return names
    except Exception as e:
        print(f'[app_volume] {e}')
        return []


# ---------------------------------------------------------------------------
# Screen brightness
# ---------------------------------------------------------------------------

def adjust_brightness(delta: int):
    """Raise or lower screen brightness by delta percent."""
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness(display=0)
        if isinstance(current, list):
            current = current[0]
        sbc.set_brightness(max(0, min(100, current + delta)), display=0)
    except Exception as e:
        print(f'[brightness] {e}')
