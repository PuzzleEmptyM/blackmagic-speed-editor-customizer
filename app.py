# app.py — Speed Editor Customizer GUI

import sys
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QComboBox, QLineEdit,
    QGroupBox, QStackedWidget,
    QTabWidget, QTabBar, QInputDialog, QMessageBox, QFileDialog, QSpinBox,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
)

import config as cfg
from actions import obs as obs_action
from actions import hotkey as hotkey_action
from actions import app_switch


# ---------------------------------------------------------------------------
# Signals bridge (HID thread → GUI thread)
# ---------------------------------------------------------------------------

class Signals(QObject):
    button_pressed        = pyqtSignal(str)        # key_name
    layer_runtime_changed = pyqtSignal(str)        # layer_id (from HID thread → GUI thread)
    device_status         = pyqtSignal(str)        # status string
    dial_mode_changed     = pyqtSignal(str, str)   # (mode, active_btn_key_name) — "" = normal


# ---------------------------------------------------------------------------
# Action category / action two-level selector data
# ---------------------------------------------------------------------------

# Each entry: (category_label, [(action_label, flat_stack_index), ...])
CATEGORY_ACTIONS = [
    ("None",        [("—", 0)]),
    ("Keyboard",    [("Hotkey", 1), ("Hold Key", 2), ("Toggle Hold", 3)]),
    ("Application", [("App Switch", 4), ("App Launch", 5)]),
    ("OBS",         [("Switch Scene", 6), ("Toggle Stream", 7),
                     ("Toggle Record", 8), ("Toggle Mic Mute", 9)]),
    ("Layer",       [("Push", 10), ("Back", 11)]),
    ("Dial",        [("System Volume", 12), ("App Volume", 13),
                     ("Brightness", 14), ("Reset", 15)]),
]

# flat_stack_index → (category_idx, action_idx_within_category)
_FLAT_TO_CAT = {
    fidx: (ci, ai)
    for ci, (_, acts) in enumerate(CATEGORY_ACTIONS)
    for ai, (_, fidx) in enumerate(acts)
}


# ---------------------------------------------------------------------------
# App picker dialog — searchable Start Menu shortcut browser
# ---------------------------------------------------------------------------

def _collect_start_menu_apps() -> list[tuple[str, str]]:
    """Return [(display_name, lnk_path), ...] from user + system Start Menu."""
    import os, glob as _glob
    folders = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]
    apps = {}
    for folder in folders:
        for lnk in _glob.glob(os.path.join(folder, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(lnk))[0]
            if name not in apps:          # user folder wins over system folder
                apps[name] = lnk
    return sorted(apps.items(), key=lambda x: x[0].lower())


class AppPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick an app")
        self.resize(380, 460)
        self.selected_path = ""

        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to search…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._apps = _collect_start_menu_apps()
        self._populate(self._apps)

    def _populate(self, items):
        self._list.clear()
        for name, path in items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        q = text.lower()
        self._populate([(n, p) for n, p in self._apps if q in n.lower()])

    def accept(self):
        item = self._list.currentItem()
        if item:
            self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        super().accept()


# ---------------------------------------------------------------------------
# Action config panel
# ---------------------------------------------------------------------------

def _wlabel(text: str) -> QLabel:
    """QLabel with word-wrap enabled — for description/hint text."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    return lbl


class ActionPanel(QWidget):
    saved = pyqtSignal()   # emitted after a button mapping is saved

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = None
        self._button_name = None
        self._layer_id = cfg.DEFAULT_LAYER_ID

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.title = QLabel("Select a button to configure")
        self.title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.title)

        # Two-level action selector: category → specific action
        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        for cat, _ in CATEGORY_ACTIONS:
            self.category_combo.addItem(cat)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        cat_row.addWidget(self.category_combo)
        layout.addLayout(cat_row)

        act_row = QHBoxLayout()
        act_row.addWidget(QLabel("Action:"))
        self.action_combo = QComboBox()
        self.action_combo.currentIndexChanged.connect(self._on_action_changed)
        act_row.addWidget(self.action_combo)
        layout.addLayout(act_row)

        self._populate_action_combo(0)   # seed with "None" category

        # Stacked pages per action type
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Page 0 — None
        self.stack.addWidget(_wlabel("This button will do nothing."))

        # Page 1 — Hotkey
        hotkey_page = QWidget()
        hkl = QVBoxLayout(hotkey_page)
        hkl.addWidget(QLabel("Hotkey (e.g. ctrl+shift+s):"))
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("ctrl+alt+t")
        hkl.addWidget(self.hotkey_input)
        hkl.addWidget(_wlabel("Separate keys with +. Use: ctrl, shift, alt, win, f1–f12, or any single letter/number."))
        self.stack.addWidget(hotkey_page)

        # Page 2 — Hold Key
        hold_page = QWidget()
        hold_l = QVBoxLayout(hold_page)
        hold_l.addWidget(QLabel("Key(s) to hold (e.g. alt):"))
        self.hold_input = QLineEdit()
        self.hold_input.setPlaceholderText("alt")
        hold_l.addWidget(self.hold_input)
        hold_l.addWidget(_wlabel("Held while the Speed Editor button is physically held. Release the button to release the key."))
        self.stack.addWidget(hold_page)

        # Page 3 — Toggle Hold
        toggle_hold_page = QWidget()
        th_l = QVBoxLayout(toggle_hold_page)
        th_l.addWidget(QLabel("Key(s) to latch (e.g. alt):"))
        self.toggle_hold_input = QLineEdit()
        self.toggle_hold_input.setPlaceholderText("alt")
        th_l.addWidget(self.toggle_hold_input)
        th_l.addWidget(_wlabel("Press once to hold the key down. Press again to release it."))
        self.stack.addWidget(toggle_hold_page)

        # Page 4 — App Switch
        app_page = QWidget()
        apl = QVBoxLayout(app_page)
        apl.addWidget(QLabel("Window title contains:"))
        self.app_input = QLineEdit()
        self.app_input.setPlaceholderText("Chrome")
        apl.addWidget(self.app_input)
        self.refresh_btn = QPushButton("Refresh window list")
        self.refresh_btn.clicked.connect(self._refresh_windows)
        apl.addWidget(self.refresh_btn)
        self.window_list = QComboBox()
        self.window_list.currentTextChanged.connect(lambda t: self.app_input.setText(t))
        apl.addWidget(self.window_list)
        self.stack.addWidget(app_page)

        # Page 5 — App Launch
        launch_page = QWidget()
        ll = QVBoxLayout(launch_page)
        ll.addWidget(QLabel("Path, shortcut (.lnk), or URI:"))
        launch_row = QHBoxLayout()
        self.launch_input = QLineEdit()
        self.launch_input.setPlaceholderText("e.g. spotify: or C:/…/app.exe")
        launch_row.addWidget(self.launch_input)
        search_btn = QPushButton("Search…")
        search_btn.setFixedWidth(65)
        search_btn.clicked.connect(self._search_apps)
        launch_row.addWidget(search_btn)
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(60)
        browse_btn.clicked.connect(self._browse_exe)
        launch_row.addWidget(browse_btn)
        ll.addLayout(launch_row)
        self.stack.addWidget(launch_page)

        # Page 3 — OBS Scene
        obs_scene_page = QWidget()
        osl = QVBoxLayout(obs_scene_page)
        osl.addWidget(QLabel("Scene name:"))
        self.obs_scene = QComboBox()
        self.obs_scene.setEditable(True)
        osl.addWidget(self.obs_scene)
        self.refresh_scenes_btn = QPushButton("Refresh scenes")
        self.refresh_scenes_btn.clicked.connect(self._refresh_scenes)
        osl.addWidget(self.refresh_scenes_btn)
        self.stack.addWidget(obs_scene_page)

        # Pages 4-6 — OBS toggles (no config needed)
        for label in ["Toggle streaming on/off.", "Toggle recording on/off.", "Toggle mic mute."]:
            self.stack.addWidget(_wlabel(label))

        # Page 7 — Layer Push
        layer_push_page = QWidget()
        lpl = QVBoxLayout(layer_push_page)
        lpl.addWidget(QLabel("Push layer (activate):"))
        self.layer_push_combo = QComboBox()
        lpl.addWidget(self.layer_push_combo)
        self.stack.addWidget(layer_push_page)

        # Layer Back
        self.stack.addWidget(_wlabel("Return to the previous layer."))

        # Dial: System Volume
        self.stack.addWidget(_wlabel("Turning the dial will adjust the system (master) volume. Pair with Dial: Reset on another button to go back to normal."))

        # Dial: App Volume
        dial_app_page = QWidget()
        dap_l = QVBoxLayout(dial_app_page)
        dap_l.addWidget(QLabel("App name (partial match, e.g. Spotify):"))
        self.dial_app_input = QLineEdit()
        self.dial_app_input.setPlaceholderText("Spotify")
        dap_l.addWidget(self.dial_app_input)
        self.refresh_audio_btn = QPushButton("Refresh audio apps")
        self.refresh_audio_btn.clicked.connect(self._refresh_audio_apps)
        dap_l.addWidget(self.refresh_audio_btn)
        self.audio_app_list = QComboBox()
        self.audio_app_list.currentTextChanged.connect(lambda t: self.dial_app_input.setText(t))
        dap_l.addWidget(self.audio_app_list)
        self.stack.addWidget(dial_app_page)

        # Dial: Brightness
        self.stack.addWidget(_wlabel("Turning the dial will adjust screen brightness. Works best on laptop displays. Some external monitors may not be supported."))

        # Dial: Reset
        self.stack.addWidget(_wlabel("Resets the dial back to its normal configured hotkey mode."))

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self.save_btn)

        self._refresh_windows()
        self._refresh_scenes()

    def _populate_action_combo(self, cat_idx: int):
        self.action_combo.blockSignals(True)
        self.action_combo.clear()
        for label, _ in CATEGORY_ACTIONS[cat_idx][1]:
            self.action_combo.addItem(label)
        self.action_combo.blockSignals(False)
        self.action_combo.setEnabled(len(CATEGORY_ACTIONS[cat_idx][1]) > 1)

    def _on_category_changed(self, cat_idx: int):
        self._populate_action_combo(cat_idx)
        self._on_action_changed(0)

    def _on_action_changed(self, act_idx: int):
        cat_idx = self.category_combo.currentIndex()
        acts = CATEGORY_ACTIONS[cat_idx][1]
        if act_idx < len(acts):
            self.stack.setCurrentIndex(acts[act_idx][1])

    def _set_flat_index(self, flat_idx: int):
        """Drive both combos from a flat stack index."""
        cat_idx, act_idx = _FLAT_TO_CAT.get(flat_idx, (0, 0))
        self.category_combo.blockSignals(True)
        self.category_combo.setCurrentIndex(cat_idx)
        self._populate_action_combo(cat_idx)
        self.category_combo.blockSignals(False)
        self.action_combo.blockSignals(True)
        self.action_combo.setCurrentIndex(act_idx)
        self.action_combo.blockSignals(False)
        self.stack.setCurrentIndex(flat_idx)

    def _current_flat_idx(self) -> int:
        cat_idx = self.category_combo.currentIndex()
        act_idx = self.action_combo.currentIndex()
        acts = CATEGORY_ACTIONS[cat_idx][1]
        return acts[act_idx][1] if act_idx < len(acts) else 0

    def _search_apps(self):
        dlg = AppPickerDialog(self)
        if dlg.exec() and dlg.selected_path:
            self.launch_input.setText(dlg.selected_path)

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select app or shortcut", "",
            "Apps & shortcuts (*.exe *.lnk);;All files (*)"
        )
        if path:
            self.launch_input.setText(path)

    def _refresh_audio_apps(self):
        from actions import system as system_action
        names = system_action.list_audio_apps()
        self.audio_app_list.clear()
        self.audio_app_list.addItems(names)

    def _refresh_windows(self):
        titles = app_switch.list_windows()
        self.window_list.clear()
        self.window_list.addItems(titles)

    def _refresh_scenes(self):
        scenes = obs_action.client.get_scenes()
        self.obs_scene.clear()
        self.obs_scene.addItems(scenes)

    def refresh_layers(self, layers: list):
        """Update layer push combo. layers = [(layer_id, layer_name), ...]"""
        self.layer_push_combo.clear()
        for lid, lname in layers:
            self.layer_push_combo.addItem(lname, lid)

    def load_button(self, button_name: str, config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID):
        self._button_name = button_name
        self._config = config
        self._layer_id = layer_id
        self.title.setText(f"Button: {button_name}")
        self.save_btn.setEnabled(True)

        action = cfg.get_button(config, button_name, layer_id)
        atype = action.get("action", cfg.ACTION_NONE)

        type_map = {
            cfg.ACTION_NONE:         0,
            cfg.ACTION_HOTKEY:       1,
            cfg.ACTION_HOLD_KEY:     2,
            cfg.ACTION_TOGGLE_HOLD:  3,
            cfg.ACTION_APP_SWITCH:   4,
            cfg.ACTION_APP_LAUNCH:   5,
            cfg.ACTION_OBS_SCENE:    6,
            cfg.ACTION_OBS_TOGGLE:   {"stream": 7, "record": 8, "mute_mic": 9},
            cfg.ACTION_LAYER_PUSH:   10,
            cfg.ACTION_LAYER_POP:    11,
            cfg.ACTION_DIAL_MODE:    {"sys_vol": 12, "app_vol": 13, "brightness": 14, "normal": 15},
        }

        if atype == cfg.ACTION_OBS_TOGGLE:
            idx = type_map[atype].get(action.get("toggle", "stream"), 7)
        elif atype == cfg.ACTION_DIAL_MODE:
            idx = type_map[atype].get(action.get("mode", "normal"), 15)
        else:
            idx = type_map.get(atype, 0)

        self._set_flat_index(idx)

        if atype == cfg.ACTION_HOTKEY:
            self.hotkey_input.setText(action.get("keys", ""))
        elif atype == cfg.ACTION_HOLD_KEY:
            self.hold_input.setText(action.get("keys", ""))
        elif atype == cfg.ACTION_TOGGLE_HOLD:
            self.toggle_hold_input.setText(action.get("keys", ""))
        elif atype == cfg.ACTION_APP_SWITCH:
            self.app_input.setText(action.get("app", ""))
        elif atype == cfg.ACTION_APP_LAUNCH:
            self.launch_input.setText(action.get("path", ""))
        elif atype == cfg.ACTION_OBS_SCENE:
            self.obs_scene.setCurrentText(action.get("scene", ""))
        elif atype == cfg.ACTION_LAYER_PUSH:
            target = action.get("layer", "")
            for i in range(self.layer_push_combo.count()):
                if self.layer_push_combo.itemData(i) == target:
                    self.layer_push_combo.setCurrentIndex(i)
                    break
        elif atype == cfg.ACTION_DIAL_MODE and action.get("mode") == "app_vol":
            self.dial_app_input.setText(action.get("app", ""))

    def _save(self):
        idx = self._current_flat_idx()
        if idx == 0:
            action = {"action": cfg.ACTION_NONE}
        elif idx == 1:
            action = {"action": cfg.ACTION_HOTKEY, "keys": self.hotkey_input.text().strip()}
        elif idx == 2:
            action = {"action": cfg.ACTION_HOLD_KEY, "keys": self.hold_input.text().strip()}
        elif idx == 3:
            action = {"action": cfg.ACTION_TOGGLE_HOLD, "keys": self.toggle_hold_input.text().strip()}
        elif idx == 4:
            action = {"action": cfg.ACTION_APP_SWITCH, "app": self.app_input.text().strip()}
        elif idx == 5:
            action = {"action": cfg.ACTION_APP_LAUNCH, "path": self.launch_input.text().strip()}
        elif idx == 6:
            action = {"action": cfg.ACTION_OBS_SCENE, "scene": self.obs_scene.currentText()}
        elif idx == 7:
            action = {"action": cfg.ACTION_OBS_TOGGLE, "toggle": "stream"}
        elif idx == 8:
            action = {"action": cfg.ACTION_OBS_TOGGLE, "toggle": "record"}
        elif idx == 9:
            action = {"action": cfg.ACTION_OBS_TOGGLE, "toggle": "mute_mic"}
        elif idx == 10:
            action = {"action": cfg.ACTION_LAYER_PUSH,
                      "layer": self.layer_push_combo.currentData() or ""}
        elif idx == 11:
            action = {"action": cfg.ACTION_LAYER_POP}
        elif idx == 12:
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "sys_vol"}
        elif idx == 13:
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "app_vol",
                      "app": self.dial_app_input.text().strip()}
        elif idx == 14:
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "brightness"}
        elif idx == 15:
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "normal"}
        else:
            return

        cfg.set_button(self._config, self._button_name, action, self._layer_id)

        # Auto-create the matching back button on the target layer
        if action.get("action") == cfg.ACTION_LAYER_PUSH:
            target = action.get("layer", "")
            if target:
                cfg.set_button(self._config, self._button_name,
                               {"action": cfg.ACTION_LAYER_POP}, target)

        cfg.save(self._config)
        self.saved.emit()


# ---------------------------------------------------------------------------
# Dial config widget
# ---------------------------------------------------------------------------

class DialConfigWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._layer_id = cfg.DEFAULT_LAYER_ID

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        header = QLabel("Dial")
        header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.addWidget(QLabel("Left"), 0, 1)
        grid.addWidget(QLabel("Right"), 0, 2)
        thresh_hdr = QLabel("Threshold")
        thresh_hdr.setToolTip("Ticks to accumulate before firing (1 = every tick, higher = less sensitive)")
        grid.addWidget(thresh_hdr, 0, 3)

        self._inputs = {}       # (mode, direction) → QLineEdit
        self._sensitivity = {}  # mode → QSpinBox
        for row, (mode, label) in enumerate([("jog", "Jog"), ("shuttle", "Shuttle"), ("scroll", "Scroll")], 1):
            grid.addWidget(QLabel(f"{label}:"), row, 0)
            for col, direction in [(1, "left"), (2, "right")]:
                inp = QLineEdit()
                inp.setPlaceholderText("e.g. left")
                inp.setFixedWidth(100)
                grid.addWidget(inp, row, col)
                self._inputs[(mode, direction)] = inp
            spin = QSpinBox()
            spin.setRange(1, 20)
            spin.setValue(1)
            spin.setFixedWidth(55)
            spin.setToolTip("Ticks per action: higher = less sensitive")
            grid.addWidget(spin, row, 3)
            self._sensitivity[mode] = spin

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        grid.addWidget(save_btn, 4, 0, 1, 4)

        layout.addLayout(grid)

    def set_layer(self, layer_id: str):
        self._layer_id = layer_id
        self._load()

    def _load(self):
        for (mode, direction), inp in self._inputs.items():
            action = cfg.get_dial_action(self._config, mode, direction, self._layer_id)
            inp.setText(action.get("keys", "") if action.get("action") == cfg.ACTION_HOTKEY else "")
        for mode, spin in self._sensitivity.items():
            spin.setValue(cfg.get_dial_sensitivity(self._config, mode, self._layer_id))

    def _save(self):
        for (mode, direction), inp in self._inputs.items():
            text = inp.text().strip()
            action = {"action": cfg.ACTION_HOTKEY, "keys": text} if text else {"action": cfg.ACTION_NONE}
            cfg.set_dial_action(self._config, mode, direction, action, self._layer_id)
        for mode, spin in self._sensitivity.items():
            cfg.set_dial_sensitivity(self._config, mode, spin.value(), self._layer_id)
        cfg.save(self._config)


# ---------------------------------------------------------------------------
# Settings tab
# ---------------------------------------------------------------------------

class SettingsTab(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        obs_group = QGroupBox("OBS WebSocket")
        obs_layout = QGridLayout(obs_group)
        obs_layout.addWidget(QLabel("Host:"), 0, 0)
        self.obs_host = QLineEdit(config["obs"]["host"])
        obs_layout.addWidget(self.obs_host, 0, 1)
        obs_layout.addWidget(QLabel("Port:"), 1, 0)
        self.obs_port = QLineEdit(str(config["obs"]["port"]))
        obs_layout.addWidget(self.obs_port, 1, 1)
        obs_layout.addWidget(QLabel("Password:"), 2, 0)
        self.obs_pass = QLineEdit(config["obs"]["password"])
        self.obs_pass.setEchoMode(QLineEdit.EchoMode.Password)
        obs_layout.addWidget(self.obs_pass, 2, 1)
        self.obs_connect_btn = QPushButton("Connect")
        self.obs_connect_btn.clicked.connect(self._connect_obs)
        obs_layout.addWidget(self.obs_connect_btn, 3, 0, 1, 2)
        self.obs_status = QLabel("Not connected")
        obs_layout.addWidget(self.obs_status, 4, 0, 1, 2)
        layout.addWidget(obs_group)

    def _connect_obs(self):
        host = self.obs_host.text()
        port = int(self.obs_port.text())
        password = self.obs_pass.text()
        self._config["obs"] = {"host": host, "port": port, "password": password}
        cfg.save(self._config)
        ok = obs_action.client.connect(host, port, password)
        if ok:
            self.obs_status.setText("Connected!")
            self.obs_status.setStyleSheet("color: green")
        else:
            self.obs_status.setText("Connection failed.")
            self.obs_status.setStyleSheet("color: red")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Speed Editor grid widget
# ---------------------------------------------------------------------------

ACTION_COLORS = {
    cfg.ACTION_NONE:         "#3a3a3a",
    cfg.ACTION_HOTKEY:       "#1a4a7a",
    cfg.ACTION_HOLD_KEY:     "#1a6a6a",
    cfg.ACTION_TOGGLE_HOLD:  "#2a5a5a",
    cfg.ACTION_APP_SWITCH:   "#1a5a2a",
    cfg.ACTION_APP_LAUNCH:   "#2a5a1a",
    cfg.ACTION_OBS_SCENE:    "#6a2a1a",
    cfg.ACTION_OBS_TOGGLE:   "#5a1a6a",
    cfg.ACTION_LAYER_PUSH:   "#7a5a1a",
    cfg.ACTION_LAYER_POP:    "#1a5a6a",
    cfg.ACTION_DIAL_MODE:    "#4a3a6a",
}

SELECTED_BORDER = "2px solid #00aaff"
DEFAULT_BORDER  = "1px solid #666"

SUBCOL_W    = 44
SPACING     = 4
W2          = 2 * SUBCOL_W + SPACING        # 92  — standard button width
W3          = 3 * SUBCOL_W + 2 * SPACING    # 140 — wide button width
BTN_H       = W2                            # 92  — square: height == width
SPACER_H    = BTN_H // 2                    # 46  — extra gap before IN/OUT row
# SHTL/JOG/SCRL center sits at the bottom edge of row 1 (CLOSE_UP row).
# Row 1 bottom = 2*BTN_H + SPACING.  Top of button = row1_bottom - BTN_H//2.
HALF_OFFSET = 2 * BTN_H + SPACING - BTN_H // 2  # 142

# (grid_row, subcol, colspan, key_name, label)
# Row 2 in both sections is a spacer row (no buttons, SPACER_H tall).
_LEFT = [
    (0, 0, 2, "SMART_INSRT",  "SMART\nINSRT"),
    (0, 2, 2, "APPND",        "APPND"),
    (0, 4, 2, "RIPL_OWR",     "RIPL\nO/WR"),
    (1, 0, 2, "CLOSE_UP",     "CLOSE\nUP"),
    (1, 2, 2, "PLACE_ON_TOP", "PLACE\nON TOP"),
    (1, 4, 2, "SRC_OWR",      "SRC\nO/WR"),
    # row 2 = spacer
    (3, 0, 3, "IN",           "IN"),
    (3, 3, 3, "OUT",          "OUT"),
    (4, 0, 2, "TRIM_IN",      "TRIM\nIN"),
    (4, 2, 2, "TRIM_OUT",     "TRIM\nOUT"),
    (4, 4, 2, "ROLL",         "ROLL"),
    (5, 0, 2, "SLIP_SRC",     "SLIP\nSRC"),
    (5, 2, 2, "SLIP_DEST",    "SLIP\nDEST"),
    (5, 4, 2, "TRANS_DUR",    "TRANS\nDUR"),
    (6, 0, 2, "CUT",          "CUT"),
    (6, 2, 2, "DIS",          "DIS"),
    (6, 4, 2, "SMTH_CUT",     "SMTH\nCUT"),
]

_MIDDLE = [
    (0, 0, 2, "ESC",          "ESC"),
    (0, 2, 2, "SYNC_BIN",     "SYNC\nBIN"),
    (0, 4, 2, "AUDIO_LEVEL",  "AUDIO\nLEVEL"),
    (0, 6, 2, "FULL_VIEW",    "FULL\nVIEW"),
    (1, 0, 2, "TRANS",        "TRANS"),
    (1, 2, 2, "SPLIT",        "SPLIT"),
    (1, 4, 2, "SNAP",         "SNAP"),
    (1, 6, 2, "RIPL_DEL",     "RIPL\nDEL"),
    # row 2 = spacer
    (3, 0, 2, "CAM7",         "CAM7"),
    (3, 2, 2, "CAM8",         "CAM8"),
    (3, 4, 2, "CAM9",         "CAM9"),
    (3, 6, 2, "LIVE_OWR",     "LIVE\nO/WR"),
    (4, 0, 2, "CAM4",         "CAM4"),
    (4, 2, 2, "CAM5",         "CAM5"),
    (4, 4, 2, "CAM6",         "CAM6"),
    (4, 6, 2, "VIDEO_ONLY",   "VIDEO\nONLY"),
    (5, 0, 2, "CAM1",         "CAM1"),
    (5, 2, 2, "CAM2",         "CAM2"),
    (5, 4, 2, "CAM3",         "CAM3"),
    (5, 6, 2, "AUDIO_ONLY",   "AUDIO\nONLY"),
    (6, 0, 8, "STOP_PLAY",    "STOP / PLAY"),
]

# Right section: absolute positions (key_name, label, x, y, w)
_RIGHT_ABS = [
    ("SOURCE",   "SOURCE",           0,               0,           W3),
    ("TIMELINE", "TIMELINE",         W3 + SPACING,    0,           W3),
    ("SHTL",     "SHTL",             0,               HALF_OFFSET, W2),
    ("JOG",      "JOG",              W2 + SPACING,    HALF_OFFSET, W2),
    ("SCRL",     "SCRL",             2*(W2+SPACING),  HALF_OFFSET, W2),
]


def _get_btn_display_label(key_name: str, original_label: str, config: dict, layer_id: str) -> str:
    action = cfg.get_button(config, key_name, layer_id)
    atype = action.get("action", cfg.ACTION_NONE)
    if atype == cfg.ACTION_NONE:
        return original_label
    elif atype == cfg.ACTION_HOTKEY:
        return action.get("keys", "").strip() or original_label
    elif atype == cfg.ACTION_HOLD_KEY:
        return f"hold: {action.get('keys', '').strip()}" or original_label
    elif atype == cfg.ACTION_TOGGLE_HOLD:
        return f"latch: {action.get('keys', '').strip()}" or original_label
    elif atype == cfg.ACTION_APP_SWITCH:
        return action.get("app", "").strip() or original_label
    elif atype == cfg.ACTION_APP_LAUNCH:
        import os
        path = action.get("path", "").strip()
        return os.path.basename(path) if path else original_label
    elif atype == cfg.ACTION_OBS_SCENE:
        return action.get("scene", "").strip() or original_label
    elif atype == cfg.ACTION_OBS_TOGGLE:
        return {"stream": "Stream", "record": "Record", "mute_mic": "Mute\nMic"}.get(
            action.get("toggle", ""), "OBS")
    elif atype == cfg.ACTION_LAYER_PUSH:
        lid = action.get("layer", "")
        lname = config.get("layers", {}).get(lid, {}).get("name", lid)
        return f"→\n{lname}"
    elif atype == cfg.ACTION_LAYER_POP:
        return "←\nBack"
    elif atype == cfg.ACTION_DIAL_MODE:
        mode = action.get("mode", "normal")
        if mode == "sys_vol":    return "Dial:\nVolume"
        if mode == "app_vol":    return f"Dial:\n{action.get('app','Vol')}"
        if mode == "brightness": return "Dial:\nBright"
        if mode == "normal":     return "Dial:\nReset"
    return original_label


def _apply_btn_style(btn: QPushButton, key_name: str, original_label: str,
                     config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID,
                     dial_active: bool = False):
    action = cfg.get_button(config, key_name, layer_id)
    atype = action.get("action", cfg.ACTION_NONE)
    color = "#9a3a9a" if dial_active else ACTION_COLORS.get(atype, "#3a3a3a")
    border = SELECTED_BORDER if btn.isChecked() else DEFAULT_BORDER
    btn.setText(_get_btn_display_label(key_name, original_label, config, layer_id))
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: {border};
            border-radius: 4px;
        }}
        QPushButton:checked {{ border: {SELECTED_BORDER}; }}
        QPushButton:hover   {{ background-color: #555; }}
    """)


class SpeedEditorWidget(QWidget):
    button_clicked = pyqtSignal(str)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self._selected = None
        self._btn_widgets = {}        # key_name → QPushButton
        self._btn_labels  = {}        # key_name → original label string
        self._active_dial_btn = None  # key_name of currently active dial override button

        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._make_grid(_LEFT,   6, spacer_row=2))
        layout.addWidget(self._make_grid(_MIDDLE, 8, spacer_row=2))
        layout.addWidget(self._make_right())
        layout.addStretch()

    def _make_grid(self, defs, num_subcols, spacer_row=None):
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setSpacing(SPACING)
        grid.setContentsMargins(0, 0, 0, 0)
        for c in range(num_subcols):
            grid.setColumnMinimumWidth(c, SUBCOL_W)
            grid.setColumnStretch(c, 0)
        if spacer_row is not None:
            grid.setRowMinimumHeight(spacer_row, SPACER_H)
        for row, col, colspan, key_name, label in defs:
            btn = QPushButton(label)
            btn.setMinimumHeight(BTN_H)
            btn.setFont(QFont("Arial", 8))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key_name: self._on_click(k))
            grid.addWidget(btn, row, col, 1, colspan)
            self._btn_widgets[key_name] = btn
            self._btn_labels[key_name]  = label
            _apply_btn_style(btn, key_name, label, self._config, self._layer_id)
        return widget

    def _make_right(self):
        total_w = W3 + SPACING + W3       # 284
        total_h = HALF_OFFSET + BTN_H     # 234
        widget = QWidget()
        widget.setMinimumSize(total_w, total_h)
        for key_name, label, x, y, w in _RIGHT_ABS:
            btn = QPushButton(label, widget)
            btn.setGeometry(x, y, w, BTN_H)
            btn.setFont(QFont("Arial", 8))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key_name: self._on_click(k))
            self._btn_widgets[key_name] = btn
            self._btn_labels[key_name]  = label
            _apply_btn_style(btn, key_name, label, self._config, self._layer_id)
        return widget

    def _on_click(self, key_name: str):
        if self._selected:
            old = self._btn_widgets.get(self._selected)
            if old:
                old.setChecked(False)
                _apply_btn_style(old, self._selected, self._btn_labels.get(self._selected, self._selected),
                                 self._config, self._layer_id,
                                 dial_active=(self._selected == self._active_dial_btn))
        self._selected = key_name
        btn = self._btn_widgets[key_name]
        btn.setChecked(True)
        _apply_btn_style(btn, key_name, self._btn_labels.get(key_name, key_name),
                         self._config, self._layer_id,
                         dial_active=(key_name == self._active_dial_btn))
        self.button_clicked.emit(key_name)

    def highlight(self, key_name: str):
        if key_name in self._btn_widgets:
            self._on_click(key_name)

    def set_layer(self, layer_id: str):
        self._layer_id = layer_id
        self.refresh_all_styles()

    def set_dial_btn(self, key_name: str | None):
        self._active_dial_btn = key_name
        self.refresh_all_styles()

    def refresh_all_styles(self):
        for key_name, btn in self._btn_widgets.items():
            _apply_btn_style(btn, key_name, self._btn_labels.get(key_name, key_name),
                             self._config, self._layer_id,
                             dial_active=(key_name == self._active_dial_btn))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Speed Editor Customizer")
        self._config = cfg.load()
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self.signals = Signals()
        self.signals.button_pressed.connect(self._on_button_pressed)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # --- Buttons tab ---
        buttons_tab = QWidget()
        btab_layout = QVBoxLayout(buttons_tab)
        btab_layout.setContentsMargins(8, 8, 8, 8)
        btab_layout.setSpacing(6)

        # Layer tab bar row
        layer_bar = QHBoxLayout()
        layer_bar.setSpacing(4)
        self.layer_tabs = QTabBar()
        self.layer_tabs.setExpanding(False)
        self.layer_tabs.currentChanged.connect(self._on_layer_tab_changed)
        layer_bar.addWidget(self.layer_tabs)
        new_layer_btn = QPushButton("+")
        new_layer_btn.setFixedWidth(32)
        new_layer_btn.setToolTip("New layer")
        new_layer_btn.clicked.connect(self._new_layer)
        layer_bar.addWidget(new_layer_btn)
        rename_layer_btn = QPushButton("Rename")
        rename_layer_btn.setFixedWidth(70)
        rename_layer_btn.clicked.connect(self._rename_layer)
        layer_bar.addWidget(rename_layer_btn)
        self.delete_layer_btn = QPushButton("Delete")
        self.delete_layer_btn.setFixedWidth(60)
        self.delete_layer_btn.clicked.connect(self._delete_layer)
        layer_bar.addWidget(self.delete_layer_btn)
        layer_bar.addStretch()
        btab_layout.addLayout(layer_bar)

        # Editor + action panel row
        editor_row = QHBoxLayout()
        self.se_widget = SpeedEditorWidget(self._config)
        self.se_widget.button_clicked.connect(self._select_button)
        editor_row.addWidget(self.se_widget, stretch=1)

        # Right: action config panel
        self.action_panel = ActionPanel()
        self.action_panel.setFixedWidth(320)
        self.action_panel.saved.connect(self.se_widget.refresh_all_styles)
        editor_row.addWidget(self.action_panel)
        btab_layout.addLayout(editor_row)

        tabs.addTab(buttons_tab, "Buttons")

        # --- Dial tab (created before _populate_layer_tabs so set_layer works) ---
        dial_outer = QWidget()
        dial_outer_layout = QVBoxLayout(dial_outer)
        dial_outer_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        dial_outer_layout.setContentsMargins(16, 16, 16, 16)
        self.dial_widget = DialConfigWidget(self._config)
        dial_outer_layout.addWidget(self.dial_widget)
        tabs.addTab(dial_outer, "Dial")

        self._runtime_layer_id = cfg.DEFAULT_LAYER_ID
        self._populate_layer_tabs()
        self.signals.layer_runtime_changed.connect(self._on_runtime_layer_changed)
        self.signals.device_status.connect(self._on_device_status)
        self.signals.dial_mode_changed.connect(self._on_dial_mode_changed)
        self._device_status = 'Waiting for Speed Editor…'
        self._dial_mode = ''

        self._status_bar = self.statusBar()
        self._status_bar.showMessage('Waiting for Speed Editor…')

        # --- Settings tab ---
        self.settings_tab = SettingsTab(self._config)
        tabs.addTab(self.settings_tab, "Settings")

        self.resize(1280, 700)

        # Connect OBS on startup
        obs_cfg = self._config["obs"]
        obs_action.client.connect(obs_cfg["host"], obs_cfg["port"], obs_cfg["password"])

    def _tab_label(self, layer_id: str, layer_name: str) -> str:
        """Tab title — ▶ marks whichever layer is currently selected for editing."""
        if layer_id == self._layer_id:
            return f"▶ {layer_name}"
        return layer_name

    def _refresh_tab_texts(self):
        for i in range(self.layer_tabs.count()):
            lid = self.layer_tabs.tabData(i)
            lname = self._config["layers"].get(lid, {}).get("name", lid)
            self.layer_tabs.setTabText(i, self._tab_label(lid, lname))

    def _populate_layer_tabs(self):
        self.layer_tabs.blockSignals(True)
        while self.layer_tabs.count():
            self.layer_tabs.removeTab(0)
        layers = cfg.get_layers(self._config)
        select_idx = 0
        for i, (lid, lname) in enumerate(layers):
            self.layer_tabs.addTab(self._tab_label(lid, lname))
            self.layer_tabs.setTabData(i, lid)
            if lid == self._layer_id:
                select_idx = i
        self.layer_tabs.setCurrentIndex(select_idx)
        self.layer_tabs.blockSignals(False)
        self.action_panel.refresh_layers(layers)
        self.delete_layer_btn.setEnabled(self._layer_id != cfg.DEFAULT_LAYER_ID)
        self.se_widget.set_layer(self._layer_id)  # always sync button labels
        self.dial_widget.set_layer(self._layer_id)

    def _on_layer_tab_changed(self, index: int):
        if index < 0:
            return
        self._layer_id = self.layer_tabs.tabData(index)
        self.se_widget.set_layer(self._layer_id)
        self.dial_widget.set_layer(self._layer_id)
        self._refresh_tab_texts()   # move ▶ to newly selected tab
        self.delete_layer_btn.setEnabled(self._layer_id != cfg.DEFAULT_LAYER_ID)

    def _on_runtime_layer_changed(self, layer_id: str):
        """Called (in GUI thread via signal) when the physical device switches layers."""
        self._runtime_layer_id = layer_id
        self._layer_id = layer_id
        self.se_widget.set_layer(layer_id)
        self.dial_widget.set_layer(layer_id)
        for i in range(self.layer_tabs.count()):
            if self.layer_tabs.tabData(i) == layer_id:
                self.layer_tabs.blockSignals(True)
                self.layer_tabs.setCurrentIndex(i)
                self.layer_tabs.blockSignals(False)
                break
        self._refresh_tab_texts()
        self.delete_layer_btn.setEnabled(layer_id != cfg.DEFAULT_LAYER_ID)

    def _new_layer(self):
        name, ok = QInputDialog.getText(self, "New Layer", "Layer name:")
        if ok and name.strip():
            cfg.add_layer(self._config, name.strip())
            cfg.save(self._config)
            self._populate_layer_tabs()
            for i in range(self.layer_tabs.count()):
                lid = self.layer_tabs.tabData(i)
                if self._config["layers"].get(lid, {}).get("name") == name.strip():
                    self.layer_tabs.setCurrentIndex(i)
                    break

    def _rename_layer(self):
        current_name = self.layer_tabs.tabText(self.layer_tabs.currentIndex()).lstrip("▶ ")
        name, ok = QInputDialog.getText(self, "Rename Layer", "New name:", text=current_name)
        if ok and name.strip():
            cfg.rename_layer(self._config, self._layer_id, name.strip())
            cfg.save(self._config)
            self._populate_layer_tabs()

    def _delete_layer(self):
        current_name = self.layer_tabs.tabText(self.layer_tabs.currentIndex()).lstrip("▶ ")
        reply = QMessageBox.question(self, "Delete Layer",
                                     f"Delete layer '{current_name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            cfg.delete_layer(self._config, self._layer_id)
            cfg.save(self._config)
            self._layer_id = cfg.DEFAULT_LAYER_ID
            self._populate_layer_tabs()
            self.layer_tabs.setCurrentIndex(0)

    _DIAL_MODE_LABELS = {
        "sys_vol":    "System Volume",
        "app_vol":    "App Volume",
        "brightness": "Brightness",
    }

    def _update_status_bar(self):
        msg = f'Speed Editor: {self._device_status}'
        if self._dial_mode:
            msg += f'  |  Dial: {self._DIAL_MODE_LABELS.get(self._dial_mode, self._dial_mode)}'
        self._status_bar.showMessage(msg)

    def _on_device_status(self, status: str):
        self._device_status = status
        self._update_status_bar()

    def _on_dial_mode_changed(self, mode: str, btn_name: str):
        self._dial_mode = mode
        self.se_widget.set_dial_btn(btn_name if mode else None)
        self._update_status_bar()

    def _select_button(self, key_name: str):
        self.action_panel.load_button(key_name, self._config, self._layer_id)

    def _on_button_pressed(self, key_name: str):
        self.se_widget.highlight(key_name)

    def refresh_button_colors(self):
        self.se_widget.refresh_all_styles()

    def get_signals(self) -> Signals:
        return self.signals


# ---------------------------------------------------------------------------
# Action dispatcher (called from HID thread)
# ---------------------------------------------------------------------------

def dispatch(button_name: str, config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID,
             on_push=None, on_pop=None, on_dial_mode=None, is_release: bool = False):
    action = cfg.get_button(config, button_name, layer_id)
    atype = action.get("action", cfg.ACTION_NONE)

    if atype == cfg.ACTION_HOLD_KEY:
        keys = action.get("keys", "")
        if is_release:
            hotkey_action.release_keys(keys)
        else:
            hotkey_action.press_keys(keys)
        return

    # All other actions only fire on press, not release
    if is_release:
        return

    if atype == cfg.ACTION_HOTKEY:
        hotkey_action.send(action.get("keys", ""))

    elif atype == cfg.ACTION_APP_SWITCH:
        app_switch.switch_to(action.get("app", ""))

    elif atype == cfg.ACTION_OBS_SCENE:
        obs_action.client.switch_scene(action.get("scene", ""))

    elif atype == cfg.ACTION_OBS_TOGGLE:
        toggle = action.get("toggle", "stream")
        if toggle == "stream":
            obs_action.client.toggle_stream()
        elif toggle == "record":
            obs_action.client.toggle_record()
        elif toggle == "mute_mic":
            obs_action.client.toggle_mute_mic()

    elif atype == cfg.ACTION_APP_LAUNCH:
        import os
        path = action.get("path", "")
        if path:
            try:
                os.startfile(path)
            except Exception as e:
                print(f'[launch] {e}')

    elif atype == cfg.ACTION_LAYER_PUSH:
        if on_push:
            on_push(action.get("layer", cfg.DEFAULT_LAYER_ID))

    elif atype == cfg.ACTION_LAYER_POP:
        if on_pop:
            on_pop()

    elif atype == cfg.ACTION_DIAL_MODE:
        if on_dial_mode:
            on_dial_mode(action.get("mode", "normal"), action.get("app", ""))
