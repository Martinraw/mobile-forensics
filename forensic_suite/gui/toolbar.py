"""Top toolbar with the suite's primary actions."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QLabel, QSizePolicy, QToolBar, QToolButton,
                               QWidget)

_STATE_STYLE = {
    "idle": "color:#8B949E; font-weight:600;",
    "ok": "color:#00E676; font-weight:600;",
    "busy": "color:#FFAB00; font-weight:600;",
    "error": "color:#FF1744; font-weight:600;",
}
_STATE_LABEL = {
    "idle": "\u25CF  AI Idle",
    "ok": "\u25CF  AI online",
    "busy": "\u25CF  AI thinking\u2026",
    "error": "\u25CF  AI offline",
}


class TopToolBar(QToolBar):
    """Primary actions plus an AI state indicator and user badge."""

    new_case_clicked = Signal()
    extract_clicked = Signal()
    import_clicked = Signal()
    export_clicked = Signal()
    search_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(18, 18))

        self._add("New Case", "\U0001F4C1", self.new_case_clicked)
        self._add("Extract", "\U0001F4F1", self.extract_clicked)
        self._add("Import", "\u2B07\uFE0F", self.import_clicked)
        self._add("Export", "\u2B06\uFE0F", self.export_clicked)
        self.addSeparator()
        self._add("Search", "\U0001F50D", self.search_clicked)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        self.ai_status = QLabel(_STATE_LABEL["idle"])
        self.ai_status.setStyleSheet(_STATE_STYLE["idle"])
        self.ai_status.setToolTip("AI assistant availability")
        self.addWidget(self.ai_status)

        self.user_label = QLabel("user: analyst")
        self.user_label.setStyleSheet("color:#8B949E;")
        self.addWidget(self.user_label)

        settings = QToolButton()
        settings.setText("\u2699\uFE0F")
        settings.setToolTip("Settings")
        settings.setCursor(Qt.PointingHandCursor)
        settings.clicked.connect(self.settings_clicked)
        self.addWidget(settings)

    def _add(self, text: str, icon: str, signal: Signal) -> QToolButton:
        btn = QToolButton()
        btn.setText(f"{icon}  {text}")
        btn.setToolTip(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(signal)
        self.addWidget(btn)
        return btn

    def set_ai_status(self, state: str) -> None:
        self.ai_status.setText(_STATE_LABEL.get(state, state))
        self.ai_status.setStyleSheet(_STATE_STYLE.get(state, _STATE_STYLE["idle"]))