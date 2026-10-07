"""Left navigation rail with device-status footer."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QLabel,
                               QToolButton, QVBoxLayout, QWidget)

NAV_ITEMS = [
    ("dashboard", "\U0001F4C2", "Dashboard"),
    ("extraction", "\U0001F4F1", "Extraction"),
    ("data", "\U0001F50D", "Data Viewer"),
    ("timeline", "\U0001F4C8", "Timeline"),
    ("reports", "\U0001F4C4", "Reports"),
    ("ai", "\U0001F916", "AI Assistant"),
    ("settings", "\u2699\uFE0F", "Settings"),
]


class Sidebar(QFrame):
    """Darkened vertical rail with exclusive section navigation."""

    navigation_requested = Signal(str)  # emits the tab key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(4)

        brand = QLabel("\U0001F50E  FORENSIC SUITE")
        brand.setObjectName("CardTitle")
        layout.addWidget(brand)
        layout.addSpacing(8)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for key, icon, label in NAV_ITEMS:
            btn = QToolButton()
            btn.setText(f"{icon}  {label}")
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(38)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            self._group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(8, 8, 8, 8)
        foot.setSpacing(4)
        devices_title = QLabel("Devices")
        devices_title.setObjectName("CardTitle")
        self.devices_label = QLabel("\u25CB  No device")
        self.devices_label.setProperty("role", "muted")
        self.devices_label.setWordWrap(True)
        foot.addWidget(devices_title)
        foot.addWidget(self.devices_label)
        layout.addWidget(footer)

        self._group.buttonClicked.connect(self._navigate)

    def _navigate(self, button: QAbstractButton) -> None:
        key = next((k for k, btn in self._buttons.items() if btn is button), None)
        if key:
            self.navigation_requested.emit(key)

    def set_active(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def set_devices(self, text: str) -> None:
        self.devices_label.setText(text)