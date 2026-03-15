# main.py — entry point

import sys
import threading

from PyQt6.QtWidgets import QApplication

from hid_layer import SpeedEditor, Key
import app as application
import config as cfg
from actions import hotkey as hotkey_action


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
            else:
                application.dispatch(key_name, config, _current_layer(),
                                     on_push=_push_layer, on_pop=_pop_layer)
            signals.button_pressed.emit(key_name)
            window.refresh_button_colors()

    import time

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
