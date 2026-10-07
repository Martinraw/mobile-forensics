"""Collapsible inspector panel: selection, hashes, custody, live log, AI."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPlainTextEdit,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)


class CollapsibleSection(QFrame):
    """A titled card whose body can be collapsed by clicking the header."""

    def __init__(self, title: str, body: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setText(f"\u25BE  {title}")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.clicked.connect(self._toggle)
        layout.addWidget(self.toggle)
        layout.addWidget(body)
        self.body = body

    def _toggle(self, checked: bool) -> None:
        self.body.setVisible(checked)
        arrow = "\u25BE" if checked else "\u25B8"
        self.toggle.setText(f"{arrow}  {self._title}")


class RightPanel(QScrollArea):
    """Thin right-hand inspector with all five collapsible sections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFixedWidth(310)

        content = QWidget()
        content.setObjectName("Panel")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title = QLabel("Inspector")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.info_list = QListWidget()
        layout.addWidget(CollapsibleSection("Selection Info", self.info_list))

        hash_body = QWidget()
        hash_lay = QVBoxLayout(hash_body)
        hash_lay.setContentsMargins(0, 0, 0, 0)
        hash_lay.setSpacing(6)
        self._md5 = "\u2014"
        self._sha = "\u2014"
        self.md5_label = QLabel(f"MD5     {self._md5}")
        self.sha_label = QLabel(f"SHA-256 {self._sha}")
        self.md5_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sha_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hash_row = QHBoxLayout()
        copy_md5 = QToolButton()
        copy_md5.setText("Copy MD5")
        copy_md5.clicked.connect(lambda: self._copy(self._md5))
        copy_sha = QToolButton()
        copy_sha.setText("Copy SHA-256")
        copy_sha.clicked.connect(lambda: self._copy(self._sha))
        hash_row.addWidget(copy_md5)
        hash_row.addWidget(copy_sha)
        hash_row.addStretch()
        hash_lay.addWidget(self.md5_label)
        hash_lay.addWidget(self.sha_label)
        hash_lay.addLayout(hash_row)
        layout.addWidget(CollapsibleSection("Hash Verification", hash_body))

        self.custody_list = QListWidget()
        layout.addWidget(CollapsibleSection("Chain of Custody", self.custody_list))

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setStyleSheet(
            "font-family:'JetBrains Mono','Consolas',monospace; font-size:11px; "
            "background:#0D1117; border:1px solid #30363D; border-radius:6px;")
        layout.addWidget(CollapsibleSection("Live Log", self.log_view))

        self.suggestions = QLabel(
            "Run an extraction or select an artifact to receive AI hints here.")
        self.suggestions.setWordWrap(True)
        self.suggestions.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(CollapsibleSection("AI Suggestions", self.suggestions))

        layout.addStretch()
        self.setWidget(content)

    # ---- presentation API ----
    def show_selection(self, info: dict) -> None:
        self.info_list.clear()
        for key, value in info.items():
            item = QListWidgetItem(f"{key}: {value}")
            item.setToolTip(str(value))
            self.info_list.addItem(item)

    def show_hashes(self, md5: str, sha: str) -> None:
        self._md5 = md5 or "\u2014"
        self._sha = sha or "\u2014"
        self.md5_label.setText(f"MD5     {self._md5}")
        self.sha_label.setText(f"SHA-256 {self._sha}")

    def add_custody(self, user: str, action: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.custody_list.insertItem(0, QListWidgetItem(f"{stamp} \u2014 {user} \u2014 {action}"))

    def log(self, message: str, color: str = "#8B949E") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendHtml(f'<span style="color:{color};">[{stamp}] {message}</span>')

    def set_suggestions(self, text: str) -> None:
        self.suggestions.setText(text)

    @staticmethod
    def _copy(value: str) -> None:
        QApplication.clipboard().setText(value)