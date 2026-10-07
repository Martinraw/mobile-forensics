"""Slim status bar showing whether a phone is currently visible to ADB."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy)

from core.device_manager import adb_available, first_ready_device


class DeviceStatusBar(QFrame):
    """One-line indicator: coloured dot + device text + Refresh button."""

    device_changed = Signal(object)  # DeviceInfo | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DeviceStatusBar")
        self.setFrameShape(QFrame.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.dot = QLabel("\u25CB")           # hollow circle by default
        self.dot.setFixedWidth(14)
        dot_font = QFont()
        dot_font.setPointSize(14)
        self.dot.setFont(dot_font)
        layout.addWidget(self.dot)

        self.text = QLabel("Checking for devices\u2026")
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.text, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(90)
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)

        # initial state
        self.refresh()

    # ---------- public API ----------
    def refresh(self) -> None:
        """Re-run the adb check and update the display."""
        installed, where = adb_available()
        if not installed:
            self.dot.setText("\u25CB")
            self.dot.setStyleSheet("color: #8B949E;")
            self.text.setText("ADB not installed \u2014 see tools/bin/README.md")
            self.text.setToolTip(where)
            self.text.setStyleSheet("color: #8B949E;")
            self.device_changed.emit(None)
            return

        device = first_ready_device()
        if device is None:
            self.dot.setText("\u25CB")
            self.dot.setStyleSheet("color: #8B949E;")
            self.text.setText("No device connected  \u2014 plug in a phone and tap 'Allow USB debugging'")
            self.text.setToolTip("")
            self.text.setStyleSheet("color: #8B949E;")
            self.device_changed.emit(None)
            return

        self.dot.setText("\u25CF")
        self.dot.setStyleSheet("color: #3FB950;")           # GitHub-ish green
        self.text.setText(f"{device.display_name}  \u2014  USB, ready")
        self.text.setToolTip(f"serial={device.serial}\nproduct={device.product}")
        self.text.setStyleSheet("color: #C9D1D9;")
        self.device_changed.emit(device)