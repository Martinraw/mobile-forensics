"""Animated dashboard stat card with count-up value."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class StatCard(QFrame):
    """Card with an icon, an animated numeric value and a caption."""

    def __init__(self, title: str, icon: str = "", accent: str = "#00E5FF",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(96)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        self.icon_label = QLabel(icon)
        self.icon_label.setStyleSheet(f"font-size: 28px; color: {accent};")
        self.icon_label.setFixedWidth(44)
        self.icon_label.setAlignment(Qt.AlignCenter)

        wrap = QVBoxLayout()
        wrap.setSpacing(0)
        self.value_label = QLabel("0")
        self.value_label.setProperty("role", "statValue")
        self.caption_label = QLabel(title)
        self.caption_label.setProperty("role", "statCaption")
        wrap.addWidget(self.value_label)
        wrap.addWidget(self.caption_label)

        layout.addWidget(self.icon_label)
        layout.addLayout(wrap)
        layout.addStretch()

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(700)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self, value: object) -> None:
        self.value_label.setText(f"{int(value):,}")

    def set_value(self, value: int) -> None:
        """Animate the counter from zero to ``value`` (formatted with commas)."""
        self._animation.stop()
        self._animation.setStartValue(0)
        self._animation.setEndValue(int(value))
        self._animation.start()

    def set_text(self, text: str) -> None:
        """Set the displayed text directly (no animation)."""
        self._animation.stop()
        self.value_label.setText(text)