# calibrate.py — click each button on the editor device photo to set positions
#
# Run this once: python calibrate.py
# Click the CENTER of each button when prompted.
# Positions are saved to button_positions.json

import json
import sys

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton

# The order we'll ask the user to click buttons
BUTTONS = [
    "SMART_INSRT", "APPND", "RIPL_OWR", "CLOSE_UP", "PLACE_ON_TOP", "SRC_OWR",
    "IN", "OUT", "TRIM_IN", "TRIM_OUT", "ROLL", "SLIP_SRC", "SLIP_DEST", "TRANS_DUR",
    "CUT", "DIS", "SMTH_CUT",
    "SOURCE", "TIMELINE",
    "SHTL", "JOG", "SCRL",
    "ESC", "SYNC_BIN", "AUDIO_LEVEL", "FULL_VIEW", "TRANS", "SPLIT", "SNAP", "RIPL_DEL",
    "CAM1", "CAM2", "CAM3", "CAM4", "CAM5", "CAM6", "CAM7", "CAM8", "CAM9",
    "LIVE_OWR", "VIDEO_ONLY", "AUDIO_ONLY", "STOP_PLAY",
]

POSITIONS_FILE = "button_positions.json"
IMAGE_FILE = "editor img.png"


class CalibrationWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Editor Device Button Calibration")
        self.positions = {}
        self.current_idx = 0
        self.clicks = []  # all clicks so we can draw dots

        self._orig_pixmap = QPixmap(IMAGE_FILE)
        self._scale = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Status bar
        status_bar = QHBoxLayout()
        self.status = QLabel()
        self.status.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.status.setStyleSheet("padding: 8px; background: #222; color: #fff;")
        status_bar.addWidget(self.status)

        self.skip_btn = QPushButton("Skip (no physical key)")
        self.skip_btn.clicked.connect(self._skip)
        status_bar.addWidget(self.skip_btn)

        self.undo_btn = QPushButton("Undo last")
        self.undo_btn.clicked.connect(self._undo)
        status_bar.addWidget(self.undo_btn)

        layout.addLayout(status_bar)

        # Image label
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.img_label)

        self._update_prompt()
        self._draw()

    def _update_prompt(self):
        if self.current_idx >= len(BUTTONS):
            self.status.setText("All done! Saving…")
            self._save()
        else:
            remaining = len(BUTTONS) - self.current_idx
            self.status.setText(
                f"[{self.current_idx + 1}/{len(BUTTONS)}]  Click: {BUTTONS[self.current_idx]}   "
                f"({remaining} remaining)"
            )

    def _draw(self):
        # Start from original and draw dots for confirmed positions
        px = self._orig_pixmap.copy()
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for name, (x, y) in self.positions.items():
            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.setBrush(QColor(0, 200, 0, 180))
            painter.drawEllipse(QPoint(x, y), 12, 12)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 6))
            painter.drawText(x - 10, y + 3, name[:6])

        painter.end()

        # Scale to fit screen
        screen = QApplication.primaryScreen().availableGeometry()
        max_w = screen.width() - 40
        max_h = screen.height() - 120
        if px.width() > max_w or px.height() > max_h:
            px = px.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._scale = px.width() / self._orig_pixmap.width()
        self.img_label.setPixmap(px)
        self.resize(px.width(), px.height() + 60)

    def mousePressEvent(self, event):
        if self.current_idx >= len(BUTTONS):
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Map click coords back to original image space
        # img_label starts at y=~50 (status bar height)
        label_pos = self.img_label.mapFromParent(event.pos())
        orig_x = int(label_pos.x() / self._scale)
        orig_y = int(label_pos.y() / self._scale)

        name = BUTTONS[self.current_idx]
        self.positions[name] = (orig_x, orig_y)
        self.current_idx += 1
        self._update_prompt()
        self._draw()

    def _skip(self):
        if self.current_idx >= len(BUTTONS):
            return
        self.current_idx += 1
        self._update_prompt()
        self._draw()

    def _undo(self):
        if self.current_idx == 0:
            return
        self.current_idx -= 1
        name = BUTTONS[self.current_idx]
        self.positions.pop(name, None)
        self._update_prompt()
        self._draw()

    def _save(self):
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(self.positions, f, indent=2)
        print(f"Saved {len(self.positions)} positions to {POSITIONS_FILE}")
        self.status.setText(f"Saved! {len(self.positions)} buttons mapped. You can close this window.")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = CalibrationWidget()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
