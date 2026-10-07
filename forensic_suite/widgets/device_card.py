"""Device information card shown on the extraction tab."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from core.device_manager import Device


class DeviceCard(QFrame):
    """Illustration + key technical attributes of a connected device."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.icon = QLabel("\U0001F4F1")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet("font-size: 46px;")

        self.model = QLabel("No device connected")
        self.model.setObjectName("CardTitle")
        self.model.setAlignment(Qt.AlignCenter)

        self.subtitle = QLabel("Detect a USB device or pick one from the bench")
        self.subtitle.setProperty("role", "muted")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)

        layout.addWidget(self.icon)
        layout.addWidget(self.model)
        layout.addWidget(self.subtitle)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(4)
        self._labels: dict[str, QLabel] = {}
        for row, key in enumerate(("Platform", "OS version", "Serial",
                                   "IMEI", "Connection", "Root access")):
            title = QLabel(key)
            title.setProperty("role", "muted")
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(title, row, 0)
            self.grid.addWidget(value, row, 1)
            self._labels[key] = value
        layout.addLayout(self.grid)

        self._device: Device | None = None

    @property
    def device(self) -> Device | None:
        return self._device

    def set_device(self, device: Device | None) -> None:
        self._device = device
        if device is None:
            self.icon.setText("\U0001F4F1")
            self.model.setText("No device connected")
            self.subtitle.setText("Detect a USB device or pick one from the bench")
            for label in self._labels.values():
                label.setText("—")
            return
        self.model.setText(device.model)
        self.subtitle.setText(device.name)
        self.icon.setText("\U0001F4F1" if device.platform == "iOS" else "\U0001F5A5\uFE0F")
        values = {
            "Platform": device.platform,
            "OS version": (f"Android {device.os_version}" if device.platform == "Android"
                           else f"iOS {device.os_version}"),
            "Serial": device.serial,
            "IMEI": device.imei or "—",
            "Connection": device.connection,
            "Root access": "Yes" if device.rooted else "No",
        }
        for key, value in values.items():
            self._labels[key].setText(value)