# main.py — entry point

import sys
import threading

from PyQt6.QtWidgets import QApplication

from hid_layer import SpeedEditor, Key, JogMode
import app as application
import config as cfg
from actions import hotkey as hotkey_action
from actions import system as system_action


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")

    window = application.MainWindow()
    window.show()

    config = window._config
    signals = window.get_signals()

    # Runtime layer stack — bottom is always default
    _layer_stack = [cfg.DEFAULT_LAYER_ID]

    # Toggle-hold state: button_name → keys_str currently latched
    _toggle_holds: dict = {}

    # Dial override: None = normal (use layer config), else {"mode": ..., "app": ...}
    _dial_override: dict | None = None

    def _set_dial_override(mode: str, app: str = ""):
        nonlocal _dial_override
        if mode == "normal":
            _dial_override = None
            print('[dial] reset to normal')
        else:
            _dial_override = {"mode": mode, "app": app}
            print(f'[dial] override → mode={mode!r} app={app!r}')

    def _current_layer():
        return _layer_stack[-1]

    def _push_layer(layer_id):
        _layer_stack.append(layer_id)
        signals.layer_runtime_changed.emit(layer_id)

    def _pop_layer():
        if len(_layer_stack) > 1:
            _layer_stack.pop()
        signals.layer_runtime_changed.emit(_current_layer())

    # Track which keys are currently held (avoid repeat firing)
    _held = set()

    def on_key(keys):
        nonlocal _held
        pressed = {k.name for k in keys}
        newly_released = _held - pressed
        newly_pressed  = pressed - _held
        _held = pressed

        for key_name in newly_released:
            application.dispatch(key_name, config, _current_layer(),
                                 on_push=_push_layer, on_pop=_pop_layer,
                                 is_release=True)

        for key_name in newly_pressed:
            action = cfg.get_button(config, key_name, _current_layer())
            print(f'[key] {key_name} → {action}  (layer={_current_layer()})')
            if action.get("action") == cfg.ACTION_TOGGLE_HOLD:
                keys_str = action.get("keys", "")
                if key_name in _toggle_holds:
                    print(f'[toggle] unlatch {keys_str!r}')
                    hotkey_action.release_keys(_toggle_holds.pop(key_name))
                else:
                    print(f'[toggle] latch {keys_str!r}')
                    hotkey_action.press_keys(keys_str)
                    _toggle_holds[key_name] = keys_str
            elif action.get("action") == cfg.ACTION_DIAL_MODE:
                mode = action.get("mode", "normal")
                # Toggle off if already active, otherwise switch to new mode
                if mode != "normal" and _dial_override and _dial_override.get("mode") == mode:
                    _set_dial_override("normal")
                    signals.dial_mode_changed.emit("", "")
                else:
                    _set_dial_override(mode, action.get("app", ""))
                    signals.dial_mode_changed.emit(mode, key_name)
            else:
                application.dispatch(key_name, config, _current_layer(),
                                     on_push=_push_layer, on_pop=_pop_layer)
            signals.button_pressed.emit(key_name)
            window.refresh_button_colors()

    import time

    _JOG_MODE_NAMES = {
        JogMode.RELATIVE:          "jog",
        JogMode.ABSOLUTE:          "shuttle",
        JogMode.RELATIVE_2:        "scroll",
        JogMode.ABSOLUTE_DEADZERO: "shuttle",
    }
    _last_shuttle_fire = [0.0]
    _jog_accum = {"jog": 0, "shuttle": 0, "scroll": 0}

    def _fire_dial(mode_name, direction):
        sign = 1 if direction == "right" else -1
        if _dial_override:
            ov = _dial_override.get("mode")
            if ov == "sys_vol":
                system_action.adjust_master_volume(sign * system_action.VOL_STEP)
            elif ov == "app_vol":
                system_action.adjust_app_volume(_dial_override.get("app", ""),
                                                sign * system_action.VOL_STEP)
            elif ov == "brightness":
                system_action.adjust_brightness(sign * system_action.BRIGHT_STEP)
        else:
            action = cfg.get_dial_action(config, mode_name, direction, _current_layer())
            if action.get("action") == cfg.ACTION_HOTKEY:
                hotkey_action.send(action.get("keys", ""))

    def on_jog(mode, value):
        if value == 0:
            return
        mode_name = _JOG_MODE_NAMES.get(mode, "jog")

        # Throttle shuttle (absolute position fires continuously while held)
        if mode_name == "shuttle":
            now = time.time()
            if now - _last_shuttle_fire[0] < 0.08:
                return
            _last_shuttle_fire[0] = now

        threshold = cfg.get_dial_sensitivity(config, mode_name, _current_layer())
        _jog_accum[mode_name] += 1 if value > 0 else -1

        if _jog_accum[mode_name] >= threshold:
            _jog_accum[mode_name] -= threshold
            _fire_dial(mode_name, "right")
        elif _jog_accum[mode_name] <= -threshold:
            _jog_accum[mode_name] += threshold
            _fire_dial(mode_name, "left")

    _se = None

    def hid_thread():
        nonlocal _se
        while True:
            try:
                se = SpeedEditor()
                _se = se
                print('[HID] Device connected.')
                signals.device_status.emit('Connected')
                se.on_key = on_key
                se.on_jog = on_jog
                se.authenticate()
                se.run()
            except OSError as e:
                print(f'[HID] Device not found, retrying in 3s… ({e})')
                signals.device_status.emit('Not connected — retrying…')
            except Exception as e:
                print(f'[HID] Error: {e}')
                signals.device_status.emit(f'Error: {e}')
            finally:
                try:
                    if _se:
                        _se.close()
                except Exception:
                    pass
                _se = None
            time.sleep(3)

    t = threading.Thread(target=hid_thread, daemon=True)
    t.start()

    exit_code = qt_app.exec()
    if _se:
        _se.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
