# config.py — load/save button mappings and app settings

import json
import os
import sys
import uuid


def _app_dir() -> str:
    """Return the directory that should hold config.json.
    When running as a PyInstaller bundle sys.frozen is set and sys.executable
    points to the .exe, so we place config.json next to it.
    When running from source, use the script directory as before."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(_app_dir(), 'config.json')

# Action types
ACTION_HOTKEY      = "hotkey"
ACTION_HOLD_KEY    = "hold_key"
ACTION_TOGGLE_HOLD = "toggle_hold"
ACTION_APP_SWITCH  = "app_switch"
ACTION_APP_LAUNCH  = "app_launch"
ACTION_OBS_SCENE   = "obs_scene"
ACTION_OBS_TOGGLE  = "obs_toggle"
ACTION_LAYER_PUSH  = "layer_push"
ACTION_LAYER_POP   = "layer_pop"
ACTION_DIAL_MODE   = "dial_mode"   # sets runtime dial override (sys_vol / app_vol / brightness / normal)
ACTION_NONE        = "none"

OBS_TOGGLE_OPTIONS = ["stream", "record", "mute_mic"]

DEFAULT_LAYER_ID = "default"

DEFAULT_CONFIG = {
    "obs": {
        "host": "localhost",
        "port": 4455,
        "password": "obsCONNECT"
    },
    "layers": {
        DEFAULT_LAYER_ID: {
            "name": "Default",
            "buttons": {}
        }
    }
}


def load() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return _deep_copy(DEFAULT_CONFIG)
    with open(CONFIG_FILE, 'r') as f:
        data = json.load(f)

    # Migrate old format (top-level "buttons") to layers
    if "buttons" in data and "layers" not in data:
        data["layers"] = {
            DEFAULT_LAYER_ID: {"name": "Default", "buttons": data.pop("buttons")}
        }

    merged = _deep_copy(DEFAULT_CONFIG)
    merged["obs"].update(data.get("obs", {}))
    merged["layers"] = data.get("layers", merged["layers"])
    return merged


def save(config: dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_button(config: dict, button_name: str, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    return (config["layers"]
            .get(layer_id, {})
            .get("buttons", {})
            .get(button_name, {"action": ACTION_NONE}))


def get_dial_sensitivity(config: dict, mode: str, layer_id: str = DEFAULT_LAYER_ID) -> int:
    """Return ticks-per-action threshold for this dial mode (default 1)."""
    return (config["layers"]
            .get(layer_id, {})
            .get("dial_sensitivity", {})
            .get(mode, 1))


def set_dial_sensitivity(config: dict, mode: str, threshold: int, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    layer = config["layers"][layer_id]
    layer.setdefault("dial_sensitivity", {})[mode] = threshold


def get_dial_action(config: dict, mode: str, direction: str, layer_id: str = DEFAULT_LAYER_ID) -> dict:
    return (config["layers"]
            .get(layer_id, {})
            .get("dial", {})
            .get(mode, {})
            .get(direction, {"action": ACTION_NONE}))


def set_dial_action(config: dict, mode: str, direction: str, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    layer = config["layers"][layer_id]
    if "dial" not in layer:
        layer["dial"] = {}
    if mode not in layer["dial"]:
        layer["dial"][mode] = {}
    layer["dial"][mode][direction] = action


def set_button(config: dict, button_name: str, action: dict, layer_id: str = DEFAULT_LAYER_ID):
    if layer_id not in config["layers"]:
        config["layers"][layer_id] = {"name": layer_id, "buttons": {}}
    config["layers"][layer_id]["buttons"][button_name] = action


def add_layer(config: dict, name: str) -> str:
    layer_id = uuid.uuid4().hex[:8]
    config["layers"][layer_id] = {"name": name, "buttons": {}}
    return layer_id


def delete_layer(config: dict, layer_id: str):
    if layer_id != DEFAULT_LAYER_ID:
        config["layers"].pop(layer_id, None)
        # Remove any layer_push references to the deleted layer
        for lid, layer in config["layers"].items():
            for btn, action in list(layer["buttons"].items()):
                if action.get("action") == ACTION_LAYER_PUSH and action.get("layer") == layer_id:
                    layer["buttons"].pop(btn)


def rename_layer(config: dict, layer_id: str, new_name: str):
    if layer_id in config["layers"]:
        config["layers"][layer_id]["name"] = new_name


def get_layers(config: dict) -> list[tuple[str, str]]:
    """Return [(layer_id, layer_name), ...] sorted with default first."""
    layers = [(k, v["name"]) for k, v in config["layers"].items()]
    layers.sort(key=lambda x: (x[0] != DEFAULT_LAYER_ID, x[1]))
    return layers


def _deep_copy(d):
    return json.loads(json.dumps(d))
