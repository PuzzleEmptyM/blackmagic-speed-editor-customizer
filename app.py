# app.py — Editor Device Customizer GUI

import sys
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QComboBox, QLineEdit,
    QGroupBox, QStackedWidget, QSlider,
    QTabWidget, QTabBar, QInputDialog, QMessageBox, QFileDialog, QSpinBox,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
    QStyledItemDelegate, QStyle,
)

import platform_layer
import config as cfg
from actions import obs as obs_action
from actions import hotkey as hotkey_action
from actions import app_switch
import auth
import cloud_sync


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
_DIAL_HW_MODE_DESCS = {
    "Jog":     "Each wheel click fires once. Best for precise, step-by-step adjustments.",
    "Shuttle": "Fires repeatedly while held off-center. Best for large, continuous sweeping changes.",
    "Scroll":  "Similar to Jog — fires once per click with a slightly different wheel feel.",
}

_FLAT_TO_CAT = {
    fidx: (ci, ai)
    for ci, (_, acts) in enumerate(CATEGORY_ACTIONS)
    for ai, (_, fidx) in enumerate(acts)
}


# ---------------------------------------------------------------------------
# Global stylesheet — navy / dark-purple Tailwind-inspired theme
# ---------------------------------------------------------------------------

GLOBAL_STYLESHEET = """
/* ── Base ──────────────────────────────────────────────────────────────────── */
QMainWindow {
    background-color: #080d18;
}
QDialog {
    background-color: #10172a;
}

/* ── Tabs (main Buttons / Settings tabs) ───────────────────────────────────── */
QTabWidget::pane {
    background-color: #080d18;
    border: 1px solid #1e2d50;
    border-radius: 0 10px 10px 10px;
}
QTabWidget > QWidget {
    background-color: #080d18;
}
QTabBar::tab {
    background-color: #10172a;
    color: #64748b;
    border: 1px solid #1e2d50;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 7px 20px;
    margin-right: 3px;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.3px;
}
QTabBar::tab:selected {
    background-color: #3730a3;
    color: #e0e7ff;
    border-color: #4338ca;
}
QTabBar::tab:hover:!selected {
    background-color: #162040;
    color: #c7d2fe;
    border-color: #4338ca;
}

/* ── Generic QPushButton ───────────────────────────────────────────────────── */
QPushButton {
    background-color: #1a2540;
    color: #c7d2fe;
    border: 1px solid #2d3f6e;
    border-radius: 7px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #243260;
    border-color: #6366f1;
    color: #e0e7ff;
}
QPushButton:pressed {
    background-color: #4338ca;
    border-color: #818cf8;
    color: #ffffff;
}
QPushButton:disabled {
    background-color: #0f1525;
    color: #334155;
    border-color: #1e2d50;
}

/* ── QLineEdit ──────────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #10172a;
    color: #e2e8f0;
    border: 1px solid #2d3f6e;
    border-radius: 7px;
    padding: 5px 10px;
    selection-background-color: #4338ca;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #6366f1;
    background-color: #131c33;
}
QLineEdit:disabled {
    color: #334155;
}

/* ── QComboBox ──────────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #1a2540;
    color: #e2e8f0;
    border: 1px solid #3d5080;
    border-radius: 7px;
    padding: 4px 10px;
    min-height: 28px;
    font-size: 13px;
}
QComboBox:hover  { border-color: #6366f1; background-color: #1e2d50; }
QComboBox:focus  { border-color: #6366f1; }
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left:  5px solid transparent;
    border-right: 5px solid transparent;
    border-top:   5px solid #94a3b8;
    margin-right: 8px;
}

/* QComboBox popup colors/hover are handled entirely by QPalette (see MainWindow.__init__) */

/* ── QGroupBox ──────────────────────────────────────────────────────────────── */
QGroupBox {
    background-color: #10172a;
    border: 1px solid #1e2d50;
    border-radius: 12px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 700;
    font-size: 11px;
    color: #64748b;
    letter-spacing: 0.8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -1px;
    color: #6366f1;
    background-color: #10172a;
    padding: 0 6px;
    text-transform: uppercase;
}

/* ── QListWidget ────────────────────────────────────────────────────────────── */
QListWidget {
    border: 1px solid #1e2d50;
    border-radius: 8px;
    outline: none;
    font-size: 13px;
}

/* ── QSlider ────────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #1e2d50;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #6366f1;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #818cf8;
    border: 2px solid #6366f1;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #a5b4fc;
    border-color: #818cf8;
}

/* ── QLabel ─────────────────────────────────────────────────────────────────── */
QLabel {
    color: #cbd5e1;
    background: transparent;
}

/* ── QStatusBar ─────────────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #10172a;
    color: #64748b;
    border-top: 1px solid #1e2d50;
    font-size: 12px;
}

/* ── QScrollBar ─────────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #10172a;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2d3f6e;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover  { background: #6366f1; }
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical      { height: 0; }

/* ── QScrollArea / generic pane backgrounds ─────────────────────────────────── */
QScrollArea { border: none; background: transparent; }

/* ── QSpinBox ───────────────────────────────────────────────────────────────── */
QSpinBox {
    background-color: #10172a;
    color: #e2e8f0;
    border: 1px solid #2d3f6e;
    border-radius: 7px;
    padding: 4px 8px;
}
QSpinBox:focus { border-color: #6366f1; }

/* ── QDialogButtonBox ───────────────────────────────────────────────────────── */
QDialogButtonBox QPushButton { min-width: 80px; }

/* ── QMessageBox ────────────────────────────────────────────────────────────── */
QMessageBox QLabel { color: #e2e8f0; }
"""


# ---------------------------------------------------------------------------
# App picker dialog — searchable installed app browser
# ---------------------------------------------------------------------------


class NewLayerDialog(QDialog):
    """Asks for a new layer name and optionally a layer to copy from."""

    _BLANK = "— Blank layer —"

    def __init__(self, existing_layers: list[tuple[str, str]], parent=None):
        """existing_layers: [(layer_id, layer_name), ...]"""
        super().__init__(parent)
        self.setWindowTitle("New Layer")
        self.setFixedWidth(340)
        self.layer_name  = ""   # result: name entered by user
        self.copy_from   = None  # result: layer_id to copy from, or None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Layer name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Editing, Gaming…")
        layout.addWidget(self._name_edit)

        layout.addWidget(QLabel("Start from:"))
        self._list = QListWidget()
        blank_item = QListWidgetItem(self._BLANK)
        blank_item.setData(Qt.ItemDataRole.UserRole, None)
        self._list.addItem(blank_item)
        for lid, lname in existing_layers:
            item = QListWidgetItem(f"Copy of '{lname}'")
            item.setData(Qt.ItemDataRole.UserRole, lid)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.setFixedHeight(min(160, 36 + 24 * self._list.count()))
        layout.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._name_edit.setFocus()

    def _on_accept(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setPlaceholderText("Please enter a name")
            return
        self.layer_name = name
        item = self._list.currentItem()
        self.copy_from = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.accept()


class AppPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick an app")
        self.resize(400, 480)
        self.selected_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

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

        self._apps = platform_layer.collect_installable_apps()
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
    lbl.setStyleSheet("color: #64748b; font-size: 12px;")
    return lbl


class _ComboHoverDelegate(QStyledItemDelegate):
    """Custom item delegate that draws hover/selection highlights for QComboBox popups."""

    def paint(self, painter, option, index):
        painter.save()
        is_hover    = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_hover or is_selected:
            painter.fillRect(option.rect, QColor("#4338ca"))
            painter.setPen(QColor("#ffffff"))
        else:
            painter.fillRect(option.rect, QColor("#1a2540"))
            painter.setPen(QColor("#e2e8f0"))
        text_rect = option.rect.adjusted(10, 0, -4, 0)
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, index.data() or "")
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(max(sh.height(), 26))
        return sh


class ActionPanel(QWidget):
    saved = pyqtSignal()   # emitted after a button mapping is saved

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = None
        self._button_name = None
        self._layer_id = cfg.DEFAULT_LAYER_ID

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top-level stack: page 0 = button config, page 1 = dial config
        self._mode_stack = QStackedWidget()
        self._mode_stack.setAutoFillBackground(False)
        outer.addWidget(self._mode_stack)

        # ── Page 0: Button config ──────────────────────────────────────────
        btn_page = QWidget()
        layout = QVBoxLayout(btn_page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.title = QLabel("Select a button to configure")
        self.title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.title.setStyleSheet("color: #c7d2fe; padding-bottom: 8px; font-size: 13px;")
        layout.addWidget(self.title)

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

        self._populate_action_combo(0)

        self.stack = QStackedWidget()
        self.stack.setAutoFillBackground(False)
        self.stack.layout().setContentsMargins(10, 8, 10, 8)
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
        hold_l.addWidget(_wlabel("Held while the controller button is physically held. Release the button to release the key."))
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

        # Page 6 — OBS Scene
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

        # Pages 7-9 — OBS toggles (no config needed)
        for label in ["Toggle streaming on/off.", "Toggle recording on/off.", "Toggle mic mute."]:
            self.stack.addWidget(_wlabel(label))

        # Page 10 — Layer Push
        layer_push_page = QWidget()
        lpl = QVBoxLayout(layer_push_page)
        lpl.addWidget(QLabel("Push layer (activate):"))
        self.layer_push_combo = QComboBox()
        lpl.addWidget(self.layer_push_combo)
        self.stack.addWidget(layer_push_page)

        # Page 11 — Layer Back
        self.stack.addWidget(_wlabel("Return to the previous layer."))

        # Page 12 — Dial: System Volume
        sv_page = QWidget()
        sv_l = QVBoxLayout(sv_page)
        sv_l.addWidget(_wlabel("Turning the dial will adjust the system (master) volume. Pair with Dial: Reset on another button to go back to normal."))
        sv_l.addWidget(QLabel("Hardware Mode:"))
        self.sys_vol_hw_mode = QComboBox()
        self.sys_vol_hw_mode.addItems(["Jog", "Shuttle", "Scroll"])
        sv_l.addWidget(self.sys_vol_hw_mode)
        self._sys_vol_mode_desc = QLabel(_DIAL_HW_MODE_DESCS["Jog"])
        self._sys_vol_mode_desc.setWordWrap(True)
        self._sys_vol_mode_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        self.sys_vol_hw_mode.currentTextChanged.connect(
            lambda t: self._sys_vol_mode_desc.setText(_DIAL_HW_MODE_DESCS.get(t, "")))
        sv_l.addWidget(self._sys_vol_mode_desc)
        sv_l.addSpacing(4)
        sv_sens_hdr = QHBoxLayout()
        sv_sens_hdr.addWidget(QLabel("Sensitivity:"))
        self._sys_vol_sens_lbl = QLabel("100")
        self._sys_vol_sens_lbl.setFixedWidth(30)
        sv_sens_hdr.addWidget(self._sys_vol_sens_lbl)
        sv_sens_hdr.addStretch()
        sv_l.addLayout(sv_sens_hdr)
        sv_sens_row = QHBoxLayout()
        sv_sens_row.addWidget(QLabel("0"))
        self.sys_vol_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self.sys_vol_sensitivity.setRange(0, 100)
        self.sys_vol_sensitivity.setValue(100)
        self.sys_vol_sensitivity.valueChanged.connect(lambda v: self._sys_vol_sens_lbl.setText(str(v)))
        sv_sens_row.addWidget(self.sys_vol_sensitivity)
        sv_sens_row.addWidget(QLabel("100"))
        sv_l.addLayout(sv_sens_row)
        self.stack.addWidget(sv_page)

        # Page 13 — Dial: App Volume
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
        dap_l.addWidget(QLabel("Hardware Mode:"))
        self.app_vol_hw_mode = QComboBox()
        self.app_vol_hw_mode.addItems(["Jog", "Shuttle", "Scroll"])
        dap_l.addWidget(self.app_vol_hw_mode)
        self._app_vol_mode_desc = QLabel(_DIAL_HW_MODE_DESCS["Jog"])
        self._app_vol_mode_desc.setWordWrap(True)
        self._app_vol_mode_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        self.app_vol_hw_mode.currentTextChanged.connect(
            lambda t: self._app_vol_mode_desc.setText(_DIAL_HW_MODE_DESCS.get(t, "")))
        dap_l.addWidget(self._app_vol_mode_desc)
        dap_l.addSpacing(4)
        av_sens_hdr = QHBoxLayout()
        av_sens_hdr.addWidget(QLabel("Sensitivity:"))
        self._app_vol_sens_lbl = QLabel("100")
        self._app_vol_sens_lbl.setFixedWidth(30)
        av_sens_hdr.addWidget(self._app_vol_sens_lbl)
        av_sens_hdr.addStretch()
        dap_l.addLayout(av_sens_hdr)
        av_sens_row = QHBoxLayout()
        av_sens_row.addWidget(QLabel("0"))
        self.app_vol_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self.app_vol_sensitivity.setRange(0, 100)
        self.app_vol_sensitivity.setValue(100)
        self.app_vol_sensitivity.valueChanged.connect(lambda v: self._app_vol_sens_lbl.setText(str(v)))
        av_sens_row.addWidget(self.app_vol_sensitivity)
        av_sens_row.addWidget(QLabel("100"))
        dap_l.addLayout(av_sens_row)
        self.stack.addWidget(dial_app_page)

        # Page 14 — Dial: Brightness
        bright_page = QWidget()
        bright_l = QVBoxLayout(bright_page)
        bright_l.addWidget(_wlabel("Turning the dial will adjust screen brightness. Works best on laptop displays. Some external monitors may not be supported."))
        bright_l.addWidget(QLabel("Hardware Mode:"))
        self.brightness_hw_mode = QComboBox()
        self.brightness_hw_mode.addItems(["Jog", "Shuttle", "Scroll"])
        bright_l.addWidget(self.brightness_hw_mode)
        self._bright_mode_desc = QLabel(_DIAL_HW_MODE_DESCS["Jog"])
        self._bright_mode_desc.setWordWrap(True)
        self._bright_mode_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        self.brightness_hw_mode.currentTextChanged.connect(
            lambda t: self._bright_mode_desc.setText(_DIAL_HW_MODE_DESCS.get(t, "")))
        bright_l.addWidget(self._bright_mode_desc)
        bright_l.addSpacing(4)
        bright_sens_hdr = QHBoxLayout()
        bright_sens_hdr.addWidget(QLabel("Sensitivity:"))
        self._bright_sens_lbl = QLabel("100")
        self._bright_sens_lbl.setFixedWidth(30)
        bright_sens_hdr.addWidget(self._bright_sens_lbl)
        bright_sens_hdr.addStretch()
        bright_l.addLayout(bright_sens_hdr)
        bright_sens_row = QHBoxLayout()
        bright_sens_row.addWidget(QLabel("0"))
        self.brightness_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self.brightness_sensitivity.setRange(0, 100)
        self.brightness_sensitivity.setValue(100)
        self.brightness_sensitivity.valueChanged.connect(lambda v: self._bright_sens_lbl.setText(str(v)))
        bright_sens_row.addWidget(self.brightness_sensitivity)
        bright_sens_row.addWidget(QLabel("100"))
        bright_l.addLayout(bright_sens_row)
        self.stack.addWidget(bright_page)

        # Page 15 — Dial: Reset
        self.stack.addWidget(_wlabel("Resets the dial back to its normal configured hotkey mode."))

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4338ca;
                color: #ffffff;
                border: 1px solid #6366f1;
                border-radius: 7px;
                padding: 7px 16px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4f46e5;
                border-color: #818cf8;
            }
            QPushButton:pressed {
                background-color: #6366f1;
            }
            QPushButton:disabled {
                background-color: #1a2540;
                color: #334155;
                border-color: #1e2d50;
            }
        """)
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self.save_btn)

        self._mode_stack.addWidget(btn_page)

        self._refresh_windows()
        self._refresh_scenes()

        # ── Page 1: Dial default config ────────────────────────────────────
        dial_page = QWidget()
        dlayout = QVBoxLayout(dial_page)
        dlayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        dlayout.setContentsMargins(14, 14, 14, 14)
        dlayout.setSpacing(8)

        dial_title = QLabel("Dial — Default Behavior")
        dial_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        dial_title.setStyleSheet("color: #c7d2fe; padding-bottom: 8px;")
        dlayout.addWidget(dial_title)
        dlayout.addWidget(_wlabel("This action runs whenever the dial is turned and no override button is active."))
        dlayout.addSpacing(6)

        dlayout.addWidget(QLabel("Default Action:"))
        self.dial_default_action = QComboBox()
        self.dial_default_action.addItems(["System Volume", "App Volume", "Brightness"])
        self.dial_default_action.currentIndexChanged.connect(self._on_dial_default_action_changed)
        dlayout.addWidget(self.dial_default_action)

        self._dial_default_app_widget = QWidget()
        daw_l = QVBoxLayout(self._dial_default_app_widget)
        daw_l.setContentsMargins(0, 4, 0, 0)
        daw_l.addWidget(QLabel("App name (partial match, e.g. Spotify):"))
        self.dial_default_app_input = QLineEdit()
        self.dial_default_app_input.setPlaceholderText("Spotify")
        daw_l.addWidget(self.dial_default_app_input)
        self._dial_default_app_widget.setVisible(False)
        dlayout.addWidget(self._dial_default_app_widget)

        dlayout.addSpacing(8)
        dlayout.addWidget(QLabel("Hardware Mode:"))
        self.dial_default_hw_mode = QComboBox()
        self.dial_default_hw_mode.addItems(["Jog", "Shuttle", "Scroll"])
        dlayout.addWidget(self.dial_default_hw_mode)
        self._dial_default_mode_desc = QLabel(_DIAL_HW_MODE_DESCS["Jog"])
        self._dial_default_mode_desc.setWordWrap(True)
        self._dial_default_mode_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        self.dial_default_hw_mode.currentTextChanged.connect(
            lambda t: self._dial_default_mode_desc.setText(_DIAL_HW_MODE_DESCS.get(t, "")))
        dlayout.addWidget(self._dial_default_mode_desc)

        dlayout.addSpacing(8)
        dial_sens_hdr = QHBoxLayout()
        dial_sens_hdr.addWidget(QLabel("Sensitivity:"))
        self.dial_sens_val_lbl = QLabel("100")
        self.dial_sens_val_lbl.setFixedWidth(30)
        dial_sens_hdr.addWidget(self.dial_sens_val_lbl)
        dial_sens_hdr.addStretch()
        dlayout.addLayout(dial_sens_hdr)
        dial_sens_row = QHBoxLayout()
        dial_sens_row.addWidget(QLabel("0"))
        self.dial_sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.dial_sensitivity_slider.setRange(0, 100)
        self.dial_sensitivity_slider.setValue(100)
        self.dial_sensitivity_slider.valueChanged.connect(
            lambda v: self.dial_sens_val_lbl.setText(str(v)))
        dial_sens_row.addWidget(self.dial_sensitivity_slider)
        dial_sens_row.addWidget(QLabel("100"))
        dlayout.addLayout(dial_sens_row)

        dlayout.addSpacing(8)
        dial_save_btn = QPushButton("Save")
        dial_save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4338ca;
                color: #ffffff;
                border: 1px solid #6366f1;
                border-radius: 7px;
                padding: 7px 16px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4f46e5;
                border-color: #818cf8;
            }
            QPushButton:pressed {
                background-color: #6366f1;
            }
        """)
        dial_save_btn.clicked.connect(self._save)
        dlayout.addWidget(dial_save_btn)

        self._mode_stack.addWidget(dial_page)

        # Apply custom hover delegate to every QComboBox in this panel
        _delegate = _ComboHoverDelegate(self)
        for cb in self.findChildren(QComboBox):
            cb.setItemDelegate(_delegate)
            cb.view().setMouseTracking(True)
            cb.view().viewport().setMouseTracking(True)

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

    def set_layer(self, layer_id: str, config: dict):
        """Called when the active layer changes; refreshes dial panel if visible."""
        self._layer_id = layer_id
        self._config = config
        if self._mode_stack.currentIndex() == 1:
            self._load_dial_default()

    def load_dial(self, config: dict, layer_id: str):
        """Switch to dial config mode and load default dial values."""
        self._config = config
        self._layer_id = layer_id
        self._mode_stack.setCurrentIndex(1)
        self._load_dial_default()

    def _load_dial_default(self):
        default = cfg.get_dial_default(self._config, self._layer_id)
        action_idx = {"sys_vol": 0, "app_vol": 1, "brightness": 2}.get(
            default.get("action", "sys_vol"), 0)
        self.dial_default_action.blockSignals(True)
        self.dial_default_action.setCurrentIndex(action_idx)
        self.dial_default_action.blockSignals(False)
        self.dial_default_app_input.setText(default.get("app", ""))
        self._update_dial_default_app_visibility()
        self.dial_default_hw_mode.setCurrentText(default.get("hw_mode", "Jog"))
        sensitivity = default.get("sensitivity", 100)
        self.dial_sensitivity_slider.blockSignals(True)
        self.dial_sensitivity_slider.setValue(sensitivity)
        self.dial_sensitivity_slider.blockSignals(False)
        self.dial_sens_val_lbl.setText(str(sensitivity))

    def _on_dial_default_action_changed(self, idx: int):
        self._update_dial_default_app_visibility()

    def _update_dial_default_app_visibility(self):
        self._dial_default_app_widget.setVisible(
            self.dial_default_action.currentIndex() == 1)

    def load_button(self, button_name: str, config: dict, layer_id: str = cfg.DEFAULT_LAYER_ID):
        self._mode_stack.setCurrentIndex(0)
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
        elif atype == cfg.ACTION_DIAL_MODE:
            sensitivity = action.get("sensitivity", 100)
            hw_mode = action.get("hw_mode", "Jog")
            mode = action.get("mode")
            if mode == "sys_vol":
                self.sys_vol_sensitivity.setValue(sensitivity)
                self.sys_vol_hw_mode.setCurrentText(hw_mode)
            elif mode == "app_vol":
                self.dial_app_input.setText(action.get("app", ""))
                self.app_vol_sensitivity.setValue(sensitivity)
                self.app_vol_hw_mode.setCurrentText(hw_mode)
            elif mode == "brightness":
                self.brightness_sensitivity.setValue(sensitivity)
                self.brightness_hw_mode.setCurrentText(hw_mode)

    def _save(self):
        # Dial default config save
        if self._mode_stack.currentIndex() == 1:
            if not self._config:
                return
            action_key = ["sys_vol", "app_vol", "brightness"][
                self.dial_default_action.currentIndex()]
            default = {
                "action":      action_key,
                "app":         self.dial_default_app_input.text().strip(),
                "hw_mode":     self.dial_default_hw_mode.currentText(),
                "sensitivity": self.dial_sensitivity_slider.value(),
            }
            cfg.set_dial_default(self._config, default, self._layer_id)
            cfg.save(self._config)
            self.saved.emit()
            return

        # Button config save
        if not self._button_name:
            return
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
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "sys_vol",
                      "hw_mode": self.sys_vol_hw_mode.currentText(),
                      "sensitivity": self.sys_vol_sensitivity.value()}
        elif idx == 13:
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "app_vol",
                      "app": self.dial_app_input.text().strip(),
                      "hw_mode": self.app_vol_hw_mode.currentText(),
                      "sensitivity": self.app_vol_sensitivity.value()}
        elif idx == 14:
            action = {"action": cfg.ACTION_DIAL_MODE, "mode": "brightness",
                      "hw_mode": self.brightness_hw_mode.currentText(),
                      "sensitivity": self.brightness_sensitivity.value()}
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
# Settings tab
# ---------------------------------------------------------------------------

class SettingsTab(QWidget):
    profile_loaded = pyqtSignal()   # emitted when a profile replaces the working layers

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Account ──────────────────────────────────────────────────────────
        account_group = QGroupBox("Account")
        account_layout = QVBoxLayout(account_group)

        self._account_email = QLabel()
        account_layout.addWidget(self._account_email)

        btn_row = QHBoxLayout()
        self._signin_btn  = QPushButton("Sign In")
        self._signout_btn = QPushButton("Sign Out")
        self._sync_btn    = QPushButton("Sync Now")
        btn_row.addWidget(self._signin_btn)
        btn_row.addWidget(self._signout_btn)
        btn_row.addWidget(self._sync_btn)
        account_layout.addLayout(btn_row)

        self._sync_status = QLabel("")
        account_layout.addWidget(self._sync_status)

        self._signin_btn.clicked.connect(self._sign_in)
        self._signout_btn.clicked.connect(self._sign_out)
        self._sync_btn.clicked.connect(self._sync_now)

        layout.addWidget(account_group)
        self._refresh_account_ui()

        # ── Profiles ──────────────────────────────────────────────────────────
        profiles_group = QGroupBox("Profiles")
        profiles_layout = QVBoxLayout(profiles_group)

        profiles_layout.addWidget(QLabel(
            "A profile is a named snapshot of all your layers. "
            "Profiles are saved to your account (sign in required).\n"
            "Use Export / Import to share profiles without an account."
        ))

        self._profiles_list = QListWidget()
        self._profiles_list.setFixedHeight(140)
        profiles_layout.addWidget(self._profiles_list)

        prof_btn_row1 = QHBoxLayout()
        self._save_profile_btn   = QPushButton("Save Current…")
        self._load_profile_btn   = QPushButton("Load Selected")
        self._delete_profile_btn = QPushButton("Delete Selected")
        prof_btn_row1.addWidget(self._save_profile_btn)
        prof_btn_row1.addWidget(self._load_profile_btn)
        prof_btn_row1.addWidget(self._delete_profile_btn)
        profiles_layout.addLayout(prof_btn_row1)

        prof_btn_row2 = QHBoxLayout()
        self._refresh_profiles_btn = QPushButton("Refresh")
        self._export_profile_btn   = QPushButton("Export JSON…")
        self._import_profile_btn   = QPushButton("Import JSON…")
        prof_btn_row2.addWidget(self._refresh_profiles_btn)
        prof_btn_row2.addWidget(self._export_profile_btn)
        prof_btn_row2.addWidget(self._import_profile_btn)
        profiles_layout.addLayout(prof_btn_row2)

        self._profiles_status = QLabel("")
        profiles_layout.addWidget(self._profiles_status)

        self._save_profile_btn.clicked.connect(self._save_profile)
        self._load_profile_btn.clicked.connect(self._load_profile)
        self._delete_profile_btn.clicked.connect(self._delete_profile)
        self._refresh_profiles_btn.clicked.connect(self._fetch_profiles)
        self._export_profile_btn.clicked.connect(self._export_profile)
        self._import_profile_btn.clicked.connect(self._import_profile)

        layout.addWidget(profiles_group)

        # ── OBS WebSocket ─────────────────────────────────────────────────────
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

    def _refresh_account_ui(self):
        signed_in = auth.is_signed_in()
        email = auth.get_user_email() or "Signed in"
        self._account_email.setText(email if signed_in else "Not signed in")
        self._signin_btn.setVisible(not signed_in)
        self._signout_btn.setVisible(signed_in)
        self._sync_btn.setEnabled(signed_in)

    def _sign_in(self):
        self._signin_btn.setEnabled(False)
        self._signin_btn.setText("Opening browser…")

        def _do():
            ok = auth.sign_in()
            self._signin_btn.setEnabled(True)
            self._signin_btn.setText("Sign In")
            if ok:
                self._refresh_account_ui()
                self._set_sync_status("Signed in. Syncing…", "gray")
                self._sync_now()
            else:
                self._set_sync_status("Sign-in timed out or was cancelled.", "red")

        threading.Thread(target=_do, daemon=True).start()

    def _sign_out(self):
        auth.sign_out()
        self._refresh_account_ui()
        self._set_sync_status("Signed out.", "gray")

    def _sync_now(self):
        if not auth.is_signed_in():
            return
        self._sync_btn.setEnabled(False)
        self._set_sync_status("Syncing…", "gray")

        def _do():
            try:
                cloud_sync.sync_from_cloud(self._config)
                self._set_sync_status("Synced successfully.", "green")
            except Exception as e:
                self._set_sync_status(f"Sync failed: {e}", "red")
            finally:
                self._sync_btn.setEnabled(True)

        threading.Thread(target=_do, daemon=True).start()

    def _set_sync_status(self, text: str, color: str):
        self._sync_status.setText(text)
        self._sync_status.setStyleSheet(f"color: {color}")

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

    # ── Profiles helpers ─────────────────────────────────────────────────────

    def _set_prof_status(self, text: str, color: str = "gray"):
        self._profiles_status.setText(text)
        self._profiles_status.setStyleSheet(f"color: {color}")

    def _fetch_profiles(self):
        if not auth.is_signed_in():
            self._set_prof_status("Sign in to view cloud profiles.", "gray")
            return
        self._refresh_profiles_btn.setEnabled(False)
        self._set_prof_status("Loading…", "gray")

        def _do():
            try:
                profiles = cloud_sync.fetch_profiles()
                self._profiles_list.clear()
                for p in profiles:
                    item = QListWidgetItem(p["name"])
                    item.setData(Qt.ItemDataRole.UserRole, p["name"])
                    self._profiles_list.addItem(item)
                self._set_prof_status(f"{len(profiles)} profile(s) found.", "green")
            except Exception as e:
                self._set_prof_status(f"Failed: {e}", "red")
            finally:
                self._refresh_profiles_btn.setEnabled(True)

        threading.Thread(target=_do, daemon=True).start()

    def _save_profile(self):
        if not auth.is_signed_in():
            self._set_prof_status("Sign in to save profiles.", "gray")
            return
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        self._save_profile_btn.setEnabled(False)
        self._set_prof_status("Saving…", "gray")

        def _do():
            try:
                cloud_sync.save_profile_to_cloud(self._config, name)
                self._set_prof_status(f"Saved '{name}'.", "green")
                self._fetch_profiles()
            except Exception as e:
                self._set_prof_status(f"Save failed: {e}", "red")
            finally:
                self._save_profile_btn.setEnabled(True)

        threading.Thread(target=_do, daemon=True).start()

    def _load_profile(self):
        item = self._profiles_list.currentItem()
        if not item:
            self._set_prof_status("Select a profile first.", "gray")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.warning(
            self, "Load Profile",
            f"Load profile '{name}'?\n\nThis will replace ALL current layers. "
            "Make sure you have saved or exported anything you want to keep.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return
        self._load_profile_btn.setEnabled(False)
        self._set_prof_status("Loading…", "gray")

        def _do():
            try:
                cloud_sync.load_profile_from_cloud(self._config, name)
                self._set_prof_status(f"Loaded '{name}'.", "green")
                self.profile_loaded.emit()
            except Exception as e:
                self._set_prof_status(f"Load failed: {e}", "red")
            finally:
                self._load_profile_btn.setEnabled(True)

        threading.Thread(target=_do, daemon=True).start()

    def _delete_profile(self):
        item = self._profiles_list.currentItem()
        if not item:
            self._set_prof_status("Select a profile first.", "gray")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{name}' from the cloud?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._delete_profile_btn.setEnabled(False)
        self._set_prof_status("Deleting…", "gray")

        def _do():
            try:
                cloud_sync.delete_profile_from_cloud(name)
                self._set_prof_status(f"Deleted '{name}'.", "green")
                self._fetch_profiles()
            except Exception as e:
                self._set_prof_status(f"Delete failed: {e}", "red")
            finally:
                self._delete_profile_btn.setEnabled(True)

        threading.Thread(target=_do, daemon=True).start()

    def _export_profile(self):
        import json as _json
        path, _ = QFileDialog.getSaveFileName(self, "Export Profile", "profile.json",
                                              "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path, "w") as f:
                _json.dump({"layers": self._config["layers"]}, f, indent=2)
            self._set_prof_status("Profile exported.", "green")
        except Exception as e:
            self._set_prof_status(f"Export failed: {e}", "red")

    def _import_profile(self):
        import json as _json
        path, _ = QFileDialog.getOpenFileName(self, "Import Profile", "",
                                              "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = _json.load(f)
            layers = data.get("layers")
            if not isinstance(layers, dict):
                raise ValueError("Invalid profile file — expected a 'layers' object.")
            reply = QMessageBox.warning(
                self, "Import Profile",
                "Import this profile?\n\nThis will replace ALL current layers. "
                "Make sure you have saved or exported anything you want to keep.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
            cfg.load_profile_into_working(self._config, layers)
            cfg.save(self._config)
            self._set_prof_status("Profile imported.", "green")
            self.profile_loaded.emit()
        except Exception as e:
            self._set_prof_status(f"Import failed: {e}", "red")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Editor device grid widget
# ---------------------------------------------------------------------------

ACTION_COLORS = {
    cfg.ACTION_NONE:         "#141c30",  # unassigned — deep navy slate
    cfg.ACTION_HOTKEY:       "#1e3a8a",  # indigo blue
    cfg.ACTION_HOLD_KEY:     "#0e4b4b",  # deep teal
    cfg.ACTION_TOGGLE_HOLD:  "#0a4060",  # dark cyan
    cfg.ACTION_APP_SWITCH:   "#14532d",  # emerald dark
    cfg.ACTION_APP_LAUNCH:   "#1a5c35",  # forest green dark
    cfg.ACTION_OBS_SCENE:    "#7c1d1d",  # deep crimson
    cfg.ACTION_OBS_TOGGLE:   "#4c1d95",  # deep violet
    cfg.ACTION_LAYER_PUSH:   "#78350f",  # amber dark
    cfg.ACTION_LAYER_POP:    "#1e3a6a",  # steel blue
    cfg.ACTION_DIAL_MODE:    "#3b0f6e",  # ultra-deep purple
}

SELECTED_BORDER = "2px solid #818cf8"
DEFAULT_BORDER  = "1px solid #2d3f6e"

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
    color = "#5b21b6" if dial_active else ACTION_COLORS.get(atype, "#141c30")
    border = SELECTED_BORDER if btn.isChecked() else DEFAULT_BORDER
    btn.setText(_get_btn_display_label(key_name, original_label, config, layer_id))
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: #e2e8f0;
            border: {border};
            border-radius: 7px;
            font-size: 9px;
            font-weight: 600;
            font-family: "Segoe UI", Arial, sans-serif;
            letter-spacing: 0.3px;
        }}
        QPushButton:checked {{ border: {SELECTED_BORDER}; background-color: {color}; }}
        QPushButton:hover   {{ background-color: rgba(99, 102, 241, 0.28); border-color: #6366f1; }}
    """)


# ---------------------------------------------------------------------------
# Dial circle widget — visual representation of the jog wheel
# ---------------------------------------------------------------------------

class DialCircle(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = False
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(300, 300)
        self.setToolTip("Dial / Jog Wheel — click to configure")

    def set_selected(self, v: bool):
        self._selected = v
        self.update()

    def set_active(self, v: bool):
        self._active = v
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = 6
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        fill = QColor("#4c1d95") if self._active else QColor("#141c30")
        border_color = QColor("#818cf8") if self._selected else QColor("#2d3f6e")
        pen_width = 3 if self._selected else 2
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(border_color, pen_width))
        painter.drawEllipse(rect)
        # Inner ring for depth
        inner_margin = 14
        inner_rect = rect.adjusted(inner_margin, inner_margin, -inner_margin, -inner_margin)
        ring_color = QColor("#6366f1") if self._active else QColor("#1e2d50")
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.setPen(QPen(ring_color, 2))
        painter.drawEllipse(inner_rect)
        # Label
        painter.setPen(QPen(QColor("#c7d2fe") if self._active else QColor("#64748b")))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "DIAL")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class SpeedEditorWidget(QWidget):
    button_clicked = pyqtSignal(str)
    dial_clicked   = pyqtSignal()

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self._selected = None
        self._btn_widgets = {}        # key_name → QPushButton
        self._btn_labels  = {}        # key_name → original label string
        self._active_dial_btn = None  # key_name of currently active dial override button

        layout = QHBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._make_grid(_LEFT,   6, spacer_row=2))
        layout.addWidget(self._make_grid(_MIDDLE, 8, spacer_row=2))

        # Right section + dial circle stacked vertically
        self._dial_circle = DialCircle()
        self._dial_circle.clicked.connect(self._on_dial_click)
        right_col = QWidget()
        right_col_layout = QVBoxLayout(right_col)
        right_col_layout.setContentsMargins(0, 0, 0, 0)
        right_col_layout.setSpacing(0)
        right_col_layout.addWidget(self._make_right())
        right_col_layout.addSpacing(48)
        right_col_layout.addWidget(self._dial_circle, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(right_col)

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
            btn.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
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
            btn.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key_name: self._on_click(k))
            self._btn_widgets[key_name] = btn
            self._btn_labels[key_name]  = label
            _apply_btn_style(btn, key_name, label, self._config, self._layer_id)
        return widget

    def _on_click(self, key_name: str):
        # Deselect dial circle if it was selected
        self._dial_circle.set_selected(False)
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

    def _on_dial_click(self):
        # Deselect any selected button
        if self._selected:
            old = self._btn_widgets.get(self._selected)
            if old:
                old.setChecked(False)
                _apply_btn_style(old, self._selected, self._btn_labels.get(self._selected, self._selected),
                                 self._config, self._layer_id,
                                 dial_active=(self._selected == self._active_dial_btn))
            self._selected = None
        self._dial_circle.set_selected(True)
        self.dial_clicked.emit()

    def highlight(self, key_name: str):
        if key_name in self._btn_widgets:
            self._on_click(key_name)

    def set_layer(self, layer_id: str):
        self._layer_id = layer_id
        self.refresh_all_styles()

    def set_dial_btn(self, key_name: str | None):
        self._active_dial_btn = key_name
        self._dial_circle.set_active(key_name is not None)
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
        self.setWindowTitle("Unbound — Editor Device Customizer")
        self._config = cfg.load()
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self.signals = Signals()
        self.signals.button_pressed.connect(self._on_button_pressed)

        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPalette, QColor
        app_instance = QApplication.instance()
        app_instance.setStyleSheet(GLOBAL_STYLESHEET)

        # Fusion style ignores QSS ::item:hover — it uses QPalette::Highlight instead.
        # Set the palette so dropdown hover/selection uses our indigo accent.
        pal = app_instance.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.Highlight,        QColor("#4338ca"))
            pal.setColor(group, QPalette.ColorRole.HighlightedText,  QColor("#ffffff"))
            pal.setColor(group, QPalette.ColorRole.Window,           QColor("#080d18"))
            pal.setColor(group, QPalette.ColorRole.WindowText,       QColor("#e2e8f0"))
            pal.setColor(group, QPalette.ColorRole.Base,             QColor("#1a2540"))
            pal.setColor(group, QPalette.ColorRole.AlternateBase,    QColor("#10172a"))
            pal.setColor(group, QPalette.ColorRole.Text,             QColor("#e2e8f0"))
            pal.setColor(group, QPalette.ColorRole.ButtonText,       QColor("#e2e8f0"))
            pal.setColor(group, QPalette.ColorRole.Button,           QColor("#1a2540"))
            pal.setColor(group, QPalette.ColorRole.Mid,              QColor("#3d5080"))
            pal.setColor(group, QPalette.ColorRole.Dark,             QColor("#1e2d50"))
            pal.setColor(group, QPalette.ColorRole.Shadow,           QColor("#080d18"))
        app_instance.setPalette(pal)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # --- Buttons tab ---
        buttons_tab = QWidget()
        buttons_tab.setStyleSheet("background-color: #080d18;")
        btab_layout = QVBoxLayout(buttons_tab)
        btab_layout.setContentsMargins(12, 12, 12, 12)
        btab_layout.setSpacing(8)

        # Layer tab bar row
        layer_bar = QHBoxLayout()
        layer_bar.setSpacing(6)
        self.layer_tabs = QTabBar()
        self.layer_tabs.setExpanding(False)
        self.layer_tabs.setStyleSheet("""
            QTabBar::tab {
                background-color: #1a2540;
                color: #64748b;
                border: 1px solid #2d3f6e;
                border-radius: 6px;
                padding: 5px 16px;
                margin-right: 3px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #3730a3;
                color: #e0e7ff;
                border-color: #4338ca;
            }
            QTabBar::tab:hover:!selected {
                background-color: #243260;
                color: #c7d2fe;
                border-color: #4338ca;
            }
        """)
        self.layer_tabs.currentChanged.connect(self._on_layer_tab_changed)
        layer_bar.addWidget(self.layer_tabs)

        _layer_btn_style = """
            QPushButton {
                background-color: #1a2540;
                color: #94a3b8;
                border: 1px solid #2d3f6e;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #243260;
                border-color: #6366f1;
                color: #e0e7ff;
            }
            QPushButton:pressed {
                background-color: #4338ca;
                color: #ffffff;
            }
            QPushButton:disabled {
                color: #334155;
                border-color: #1e2d50;
                background-color: #0f1525;
            }
        """

        new_layer_btn = QPushButton("+")
        new_layer_btn.setFixedWidth(34)
        new_layer_btn.setToolTip("New layer")
        new_layer_btn.setStyleSheet(_layer_btn_style)
        new_layer_btn.clicked.connect(self._new_layer)
        layer_bar.addWidget(new_layer_btn)
        rename_layer_btn = QPushButton("Rename")
        rename_layer_btn.setFixedWidth(72)
        rename_layer_btn.setStyleSheet(_layer_btn_style)
        rename_layer_btn.clicked.connect(self._rename_layer)
        layer_bar.addWidget(rename_layer_btn)
        self.delete_layer_btn = QPushButton("Delete")
        self.delete_layer_btn.setFixedWidth(64)
        self.delete_layer_btn.setStyleSheet(_layer_btn_style)
        self.delete_layer_btn.clicked.connect(self._delete_layer)
        layer_bar.addWidget(self.delete_layer_btn)
        export_layer_btn = QPushButton("Export…")
        export_layer_btn.setFixedWidth(72)
        export_layer_btn.setToolTip("Export this layer to a JSON file")
        export_layer_btn.setStyleSheet(_layer_btn_style)
        export_layer_btn.clicked.connect(self._export_layer)
        layer_bar.addWidget(export_layer_btn)
        import_layer_btn = QPushButton("Import…")
        import_layer_btn.setFixedWidth(72)
        import_layer_btn.setToolTip("Import a layer from a JSON file")
        import_layer_btn.setStyleSheet(_layer_btn_style)
        import_layer_btn.clicked.connect(self._import_layer)
        layer_bar.addWidget(import_layer_btn)
        layer_bar.addStretch()
        btab_layout.addLayout(layer_bar)

        # Editor + action panel row
        editor_row = QHBoxLayout()
        editor_row.setSpacing(12)

        # Speed editor area — dark card
        se_card = QWidget()
        se_card.setStyleSheet("""
            QWidget {
                background-color: #0c1220;
                border: 1px solid #1e2d50;
                border-radius: 12px;
            }
        """)
        se_card_layout = QVBoxLayout(se_card)
        se_card_layout.setContentsMargins(8, 8, 8, 8)
        self.se_widget = SpeedEditorWidget(self._config)
        self.se_widget.setStyleSheet("background: transparent; border: none;")
        self.se_widget.button_clicked.connect(self._select_button)
        self.se_widget.dial_clicked.connect(self._select_dial)
        se_card_layout.addWidget(self.se_widget)
        editor_row.addWidget(se_card, stretch=1)

        # Right: action config panel — dark sidebar card
        self.action_panel = ActionPanel()
        self.action_panel.setFixedWidth(330)
        self.action_panel.setStyleSheet("""
            ActionPanel {
                background-color: #10172a;
                border: 1px solid #1e2d50;
                border-radius: 12px;
            }
        """)
        self.action_panel.setAutoFillBackground(False)
        self.action_panel.saved.connect(self.se_widget.refresh_all_styles)
        editor_row.addWidget(self.action_panel)
        btab_layout.addLayout(editor_row)

        tabs.addTab(buttons_tab, "Buttons")

        self._runtime_layer_id = cfg.DEFAULT_LAYER_ID
        self._populate_layer_tabs()
        self.signals.layer_runtime_changed.connect(self._on_runtime_layer_changed)
        self.signals.device_status.connect(self._on_device_status)
        self.signals.dial_mode_changed.connect(self._on_dial_mode_changed)
        self._device_status = 'Waiting for device…'
        self._dial_mode = ''

        self._status_bar = self.statusBar()
        self._status_bar.showMessage('Waiting for device…')

        # --- Settings tab ---
        self.settings_tab = SettingsTab(self._config)
        self.settings_tab.setStyleSheet("background-color: #080d18;")
        self.settings_tab.profile_loaded.connect(self._on_profile_loaded)
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
        self.se_widget.set_layer(self._layer_id)
        self.action_panel.set_layer(self._layer_id, self._config)

    def _on_layer_tab_changed(self, index: int):
        if index < 0:
            return
        self._layer_id = self.layer_tabs.tabData(index)
        self.se_widget.set_layer(self._layer_id)
        self.action_panel.set_layer(self._layer_id, self._config)
        self._refresh_tab_texts()
        self.delete_layer_btn.setEnabled(self._layer_id != cfg.DEFAULT_LAYER_ID)

    def _on_runtime_layer_changed(self, layer_id: str):
        """Called (in GUI thread via signal) when the physical device switches layers."""
        self._runtime_layer_id = layer_id
        self._layer_id = layer_id
        self.se_widget.set_layer(layer_id)
        self.action_panel.set_layer(layer_id, self._config)
        for i in range(self.layer_tabs.count()):
            if self.layer_tabs.tabData(i) == layer_id:
                self.layer_tabs.blockSignals(True)
                self.layer_tabs.setCurrentIndex(i)
                self.layer_tabs.blockSignals(False)
                break
        self._refresh_tab_texts()
        self.delete_layer_btn.setEnabled(layer_id != cfg.DEFAULT_LAYER_ID)

    def _new_layer(self):
        existing = cfg.get_layers(self._config)
        dlg = NewLayerDialog(existing, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_id = cfg.add_layer(self._config, dlg.layer_name)
        if dlg.copy_from:
            import json as _json
            source = self._config["layers"].get(dlg.copy_from, {})
            self._config["layers"][new_id] = _json.loads(_json.dumps(source))
            self._config["layers"][new_id]["name"] = dlg.layer_name
        cfg.save(self._config)
        self._populate_layer_tabs()
        for i in range(self.layer_tabs.count()):
            if self.layer_tabs.tabData(i) == new_id:
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

    def _export_layer(self):
        import json as _json
        layer_data = self._config["layers"].get(self._layer_id, {})
        layer_name = layer_data.get("name", self._layer_id)
        path, _ = QFileDialog.getSaveFileName(self, "Export Layer", f"{layer_name}.json",
                                              "JSON files (*.json)")
        if not path:
            return
        with open(path, "w") as f:
            _json.dump({"layer": layer_data}, f, indent=2)

    def _import_layer(self):
        import json as _json
        path, _ = QFileDialog.getOpenFileName(self, "Import Layer", "",
                                              "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = _json.load(f)
            layer_data = data.get("layer") or data  # support bare layer dict too
            name = layer_data.get("name", "Imported")
            new_id = cfg.add_layer(self._config, name)
            self._config["layers"][new_id] = layer_data
            self._config["layers"][new_id]["name"] = name  # ensure name is set
            cfg.save(self._config)
            self._populate_layer_tabs()
            for i in range(self.layer_tabs.count()):
                if self.layer_tabs.tabData(i) == new_id:
                    self.layer_tabs.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.warning(self, "Import Failed", str(e))

    _DIAL_MODE_LABELS = {
        "sys_vol":    "System Volume",
        "app_vol":    "App Volume",
        "brightness": "Brightness",
    }

    def _update_status_bar(self):
        msg = f'Device: {self._device_status}'
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

    def _select_dial(self):
        self.action_panel.load_dial(self._config, self._layer_id)

    def _on_profile_loaded(self):
        """Called when SettingsTab loads a profile — rebuilds the layer tabs."""
        self._layer_id = cfg.DEFAULT_LAYER_ID
        self._populate_layer_tabs()
        self.layer_tabs.setCurrentIndex(0)

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
        path = action.get("path", "")
        if path:
            try:
                platform_layer.launch_app(path)
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
