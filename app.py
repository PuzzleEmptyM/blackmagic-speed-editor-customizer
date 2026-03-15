# app.py — Speed Editor Customizer GUI

import sys
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QComboBox, QLineEdit,
    QGroupBox, QStackedWidget,
    QTabWidget, QTabBar, QInputDialog, QMessageBox,
)

import config as cfg
from actions import obs as obs_action
from actions import hotkey as hotkey_action
from actions import app_switch


# ---------------------------------------------------------------------------
# Signals bridge (HID thread → GUI thread)
# ---------------------------------------------------------------------------

class Signals(QObject):
    button_pressed        = pyqtSignal(str)   # key_name
    layer_runtime_changed = pyqtSignal(str)   # layer_id (from HID thread → GUI thread)
    device_status         = pyqtSignal(str)   # status string (from HID thread → GUI thread)


# ---------------------------------------------------------------------------
# Action config panel
# ---------------------------------------------------------------------------

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

        # Action type selector
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Action:"))
        self.action_type = QComboBox()
        self.action_type.addItems(["None", "Hotkey", "Hold Key", "Toggle Hold", "App Switch", "OBS: Switch Scene", "OBS: Toggle Stream", "OBS: Toggle Record", "OBS: Toggle Mic Mute", "Layer: Push", "Layer: Back"])
        self.action_type.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self.action_type)
        layout.addLayout(type_row)

        # Stacked pages per action type
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Page 0 — None
        self.stack.addWidget(QLabel("This button will do nothing."))

        # Page 1 — Hotkey
        hotkey_page = QWidget()
        hkl = QVBoxLayout(hotkey_page)
        hkl.addWidget(QLabel("Hotkey (e.g. ctrl+shift+s):"))
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("ctrl+alt+t")
        hkl.addWidget(self.hotkey_input)
        hkl.addWidget(QLabel("Separate keys with +. Use: ctrl, shift, alt, win,\nf1-f12, or any single letter/number."))
        self.stack.addWidget(hotkey_page)

        # Page 2 — Hold Key
        hold_page = QWidget()
        hold_l = QVBoxLayout(hold_page)
        hold_l.addWidget(QLabel("Key(s) to hold (e.g. alt):"))
        self.hold_input = QLineEdit()
        self.hold_input.setPlaceholderText("alt")
        hold_l.addWidget(self.hold_input)
        hold_l.addWidget(QLabel("Held while the Speed Editor button is physically held.\nRelease the button to release the key."))
        self.stack.addWidget(hold_page)

        # Page 3 — Toggle Hold
        toggle_hold_page = QWidget()
        th_l = QVBoxLayout(toggle_hold_page)
        th_l.addWidget(QLabel("Key(s) to latch (e.g. alt):"))
        self.toggle_hold_input = QLineEdit()
        self.toggle_hold_input.setPlaceholderText("alt")
        th_l.addWidget(self.toggle_hold_input)
        th_l.addWidget(QLabel("Press once to hold the key down.\nPress again to release it."))
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
            self.stack.addWidget(QLabel(label))

        # Page 7 — Layer Push
        layer_push_page = QWidget()
        lpl = QVBoxLayout(layer_push_page)
        lpl.addWidget(QLabel("Push layer (activate):"))
        self.layer_push_combo = QComboBox()
        lpl.addWidget(self.layer_push_combo)
        self.stack.addWidget(layer_push_page)

        # Page 8 — Layer Back
        self.stack.addWidget(QLabel("Return to the previous layer."))

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self.save_btn)

        self._refresh_windows()
        self._refresh_scenes()

    def _on_type_changed(self, idx):
        self.stack.setCurrentIndex(idx)

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
            cfg.ACTION_OBS_SCENE:    5,
            cfg.ACTION_OBS_TOGGLE:   {"stream": 6, "record": 7, "mute_mic": 8},
            cfg.ACTION_LAYER_PUSH:   9,
            cfg.ACTION_LAYER_POP:    10,
        }

        if atype == cfg.ACTION_OBS_TOGGLE:
            idx = type_map[atype].get(action.get("toggle", "stream"), 6)
        else:
            idx = type_map.get(atype, 0)

        self.action_type.setCurrentIndex(idx)
        self.stack.setCurrentIndex(idx)

        if atype == cfg.ACTION_HOTKEY:
            self.hotkey_input.setText(action.get("keys", ""))
        elif atype == cfg.ACTION_HOLD_KEY:
            self.hold_input.setText(action.get("keys", ""))
        elif atype == cfg.ACTION_TOGGLE_HOLD:
            self.toggle_hold_input.setText(action.get("keys", ""))
        elif atype == cfg.ACTION_APP_SWITCH:
            self.app_input.setText(action.get("app", ""))
        elif atype == cfg.ACTION_OBS_SCENE:
            self.obs_scene.setCurrentText(action.get("scene", ""))
        elif atype == cfg.ACTION_LAYER_PUSH:
            target = action.get("layer", "")
            for i in range(self.layer_push_combo.count()):
                if self.layer_push_combo.itemData(i) == target:
                    self.layer_push_combo.setCurrentIndex(i)
                    break

    def _save(self):
        idx = self.action_type.currentIndex()
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
            action = {"action": cfg.ACTION_OBS_SCENE, "scene": self.obs_scene.currentText()}
        elif idx == 6:
            action = {"action": cfg.ACTION_OBS_TOGGLE, "toggle": "stream"}
        elif idx == 7:
            action = {"action": cfg.ACTION_OBS_TOGGLE, "toggle": "record"}
        elif idx == 8:
            action = {"action": cfg.ACTION_OBS_TOGGLE, "toggle": "mute_mic"}
        elif idx == 9:
            action = {"action": cfg.ACTION_LAYER_PUSH,
                      "layer": self.layer_push_combo.currentData() or ""}
        elif idx == 10:
            action = {"action": cfg.ACTION_LAYER_POP}
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
    cfg.ACTION_OBS_SCENE:   "#6a2a1a",
    cfg.ACTION_OBS_TOGGLE:  "#5a1a6a",
    cfg.ACTION_LAYER_PUSH:  "#7a5a1a",
    cfg.ACTION_LAYER_POP:   "#1a5a6a",
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
    return original_label


def _apply_btn_style(btn: QPushButton, key_name: str, original_label: str,
                     config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID):
    action = cfg.get_button(config, key_name, layer_id)
    atype = action.get("action", cfg.ACTION_NONE)
    color = ACTION_COLORS.get(atype, "#3a3a3a")
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
        self._btn_widgets = {}   # key_name → QPushButton
        self._btn_labels  = {}   # key_name → original label string

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
                                 self._config, self._layer_id)
        self._selected = key_name
        btn = self._btn_widgets[key_name]
        btn.setChecked(True)
        _apply_btn_style(btn, key_name, self._btn_labels.get(key_name, key_name),
                         self._config, self._layer_id)
        self.button_clicked.emit(key_name)

    def highlight(self, key_name: str):
        if key_name in self._btn_widgets:
            self._on_click(key_name)

    def set_layer(self, layer_id: str):
        self._layer_id = layer_id
        self.refresh_all_styles()

    def refresh_all_styles(self):
        for key_name, btn in self._btn_widgets.items():
            _apply_btn_style(btn, key_name, self._btn_labels.get(key_name, key_name),
                             self._config, self._layer_id)


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

        self._runtime_layer_id = cfg.DEFAULT_LAYER_ID
        self._populate_layer_tabs()
        self.signals.layer_runtime_changed.connect(self._on_runtime_layer_changed)
        self.signals.device_status.connect(self._on_device_status)

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

    def _on_layer_tab_changed(self, index: int):
        if index < 0:
            return
        self._layer_id = self.layer_tabs.tabData(index)
        self.se_widget.set_layer(self._layer_id)
        self._refresh_tab_texts()   # move ▶ to newly selected tab
        self.delete_layer_btn.setEnabled(self._layer_id != cfg.DEFAULT_LAYER_ID)

    def _on_runtime_layer_changed(self, layer_id: str):
        """Called (in GUI thread via signal) when the physical device switches layers."""
        self._runtime_layer_id = layer_id
        self._layer_id = layer_id
        self.se_widget.set_layer(layer_id)
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

    def _on_device_status(self, status: str):
        self._status_bar.showMessage(f'Speed Editor: {status}')

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
             on_push=None, on_pop=None, is_release: bool = False):
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

    elif atype == cfg.ACTION_LAYER_PUSH:
        if on_push:
            on_push(action.get("layer", cfg.DEFAULT_LAYER_ID))

    elif atype == cfg.ACTION_LAYER_POP:
        if on_pop:
            on_pop()
