"""Data Viewer: clickable category tree + rich searchable table."""
from __future__ import annotations

import hashlib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from widgets.data_table import DataTable

CATEGORIES = [
    ("Call Logs", "calls", "\U0001F4DE"),
    ("Messages", "messages", "\U0001F4AC"),
    ("Contacts", "contacts", "\U0001F465"),
    ("Media", "media", "\U0001F4F7"),
    ("Locations", "locations", "\U0001F4CD"),
    ("Apps", "apps", "\U0001F4E6"),
    ("Cloud Data", "cloud", "\u2601\uFE0F"),
    ("Deleted Items", "deleted", "\U0001F5D1\uFE0F"),
]

_HEADERS = {
    "calls": ["Timestamp", "Number", "Direction", "Duration"],
    "messages": ["Timestamp", "From", "To", "Content"],
    "contacts": ["Name", "Phone", "Email"],
    "media": ["Timestamp", "File", "Type", "Size"],
    "locations": ["Timestamp", "Coordinates", "Place"],
    "apps": ["Package", "Version", "Installed"],
    "cloud": ["Service", "Item", "Last Modified"],
    "deleted": ["Recovered from", "Type", "Content"],
}

_MOCK_ROWS = {
    "calls": [
        ["2024-02-05 09:30", "+260 97 123 4567", "Incoming", "84 s"],
        ["2024-02-04 20:00", "+260 96 765 4321", "Outgoing", "12 m"],
        ["2024-02-03 08:15", "+260 77 555 1212", "Missed", "\u2014"],
    ],
    "messages": [
        ["2024-02-05 10:12", "Alice Mwamba", "You", "Meet at 10am tomorrow?"],
        ["2024-02-05 10:15", "You", "Alice Mwamba", "Sure, the usual caf\u00e9."],
        ["2024-02-04 22:01", "Brian Tembo", "You", "Send the files now."],
        ["2024-02-03 18:44", "WhatsApp", "You", "Voice note (0:42)"],
    ],
    "contacts": [
        ["Alice Mwamba", "+260 97 123 4567", "alice@example.com"],
        ["Brian Tembo", "+260 96 765 4321", "brian@example.com"],
        ["Carol Banda", "+260 77 555 1212", "carol.b@example.com"],
    ],
    "media": [
        ["2024-02-01 14:03", "IMG_20240201.jpg", "Photo", "2.4 MB"],
        ["2024-02-03 19:21", "VID_20240203.mp4", "Video", "184 MB"],
        ["2024-02-05 07:55", "IMG_20240205.jpg", "Photo", "1.8 MB"],
    ],
    "locations": [
        ["2024-02-02 12:00", "-15.3875, 28.3228", "Lusaka CBD"],
        ["2024-02-04 16:30", "-15.4214, 28.2873", "East Park Mall"],
    ],
    "apps": [
        ["com.whatsapp", "2.24.1", "2024-01-20"],
        ["org.telegram.messenger", "10.3", "2024-01-22"],
        ["com.instagram.android", "328", "2024-02-01"],
    ],
    "cloud": [
        ["Google Drive", "case_notes.pdf", "2024-02-04"],
        ["Google Drive", "backup_0211.zip", "2024-02-05"],
    ],
    "deleted": [
        ["msgstore.db (WAL)", "Message", "Recovered message #1"],
        ["call_log.db", "Call", "Recovered call #2"],
        ["thumbnail cache", "Media", "IMG_20240128.jpg"],
    ],
}


class DataViewerTab(QWidget):
    """Left tree of evidence categories; right pane shows the data."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._on_select = None  # set by the main window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        heading = QLabel("\U0001F50D  Data Viewer")
        heading.setObjectName("SectionTitle")
        self.case_label = QLabel("Case: \u2014")
        self.case_label.setProperty("role", "muted")
        refresh = QPushButton("Refresh")
        refresh.setObjectName("Ghost")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self._reload)
        toolbar.addWidget(heading)
        toolbar.addStretch()
        toolbar.addWidget(self.case_label)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._category_clicked)
        splitter.addWidget(self.tree)

        self.table = DataTable()
        splitter.addWidget(self.table)
        splitter.setSizes([240, 720])
        self.table.table.itemSelectionChanged.connect(self._row_selected)
        layout.addWidget(splitter, 1)

        self._populate_tree("SIMULATED-BENCH-01")

    def _populate_tree(self, device_name: str) -> None:
        self.tree.clear()
        root = QTreeWidgetItem([f"\U0001F4F1  {device_name}"])
        root.setFlags(root.flags())
        self.tree.addTopLevelItem(root)
        self._items = {}
        for key, label, icon in CATEGORIES:
            item = QTreeWidgetItem([f"{icon}  {label}"])
            item.setData(0, Qt.UserRole, key)
            root.addChild(item)
            self._items[key] = item
        root.setExpanded(True)

    def _category_clicked(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.UserRole)
        if not key:
            return
        rows = _MOCK_ROWS.get(key, [])
        self.table.set_data(_HEADERS.get(key, ["Value"]), rows)
        self.ctx.log(f"Opened category: {key} ({len(rows)} rows)", "#00E5FF")

    def _row_selected(self) -> None:
        row = self.table.selected_row()
        if row is None or self._on_select is None:
            return
        blob = "|".join(str(v) for v in row.values()).encode("utf-8")
        md5 = hashlib.md5(blob).hexdigest()
        sha = hashlib.sha256(blob).hexdigest()
        self._on_select(row, md5, sha)

    def _reload(self) -> None:
        self._populate_tree("SIMULATED-BENCH-01")
        self.ctx.log("Data viewer refreshed", "#8B949E")

    def set_selection_callback(self, callback) -> None:
        self._on_select = callback

    def set_case(self, case_id: str) -> None:
        self.case_label.setText(f"Case: {case_id}")
        self.ctx.log(f"Viewing case {case_id}", "#8B949E")