"""Clickable icon tile used on the Home and Overview pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Tile(QFrame):
    """Icon + title + optional count. Emits ``clicked``; greyed out when disabled."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, subtitle: str = "", count: str | int | None = None,
                 enabled: bool = True, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setEnabled(enabled)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)
        if tooltip:
            self.setToolTip(tooltip)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        self.icon = QLabel(icon)
        self.icon.setStyleSheet("font-size:26px; background:transparent;")
        row.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:600; color:#E6EDF3; background:transparent;")
        col.addWidget(self.title)
        self.sub = QLabel(subtitle or ("" if count is None else str(count)))
        self.sub.setProperty("role", "muted")
        self.sub.setStyleSheet("background:transparent;")
        self.sub.setVisible(bool(self.sub.text()))
        col.addWidget(self.sub)
        row.addLayout(col, 1)
        if count is not None and subtitle:
            self.count = QLabel(f"{count:,}" if isinstance(count, int) else str(count))
            self.count.setStyleSheet("color:#00E5FF; font-weight:700; background:transparent;")
            row.addWidget(self.count)

    def set_count(self, count: int) -> None:
        self.sub.setText(f"{count:,}")
        self.sub.setVisible(True)

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
