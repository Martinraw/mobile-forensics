"""Data Viewer: real SQLite-backed category tree + searchable table.

No mock data — every row comes from the Artifact table for the active case.
"""
from __future__ import annotations

import hashlib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from widgets.data_table import DataTable

# (label, db_category, icon). Order matches the extraction writer.
CATEGORIES = [
    ("Call Logs",    "calls",     "\U0001F4DE"),
    ("Messages",     "sms",       "\U0001F4AC"),
    ("Contacts",     "contacts",  "\U0001F465"),
    ("Media",        "media",     "\U0001F4F7"),
    ("Locations",    "locations", "\U0001F4CD"),
    ("Apps",         "apps",      "\U0001F4E6"),
    ("Cloud Data",   "cloud",     "\u2601\uFE0F"),
    ("Deleted Items","deleted",   "\U0001F5D1\uFE0F"),
]

# Columns are keyed by db_category. Every artifact type has its own shape;
# unknown categories fall back to Timestamp/Source/Content.
_HEADERS = {
    "calls":     ["Timestamp", "Number", "Sender", "Recipient", "Source"],
    "sms":       ["Timestamp", "Sender", "Recipient", "Content", "Source"],
    "contacts":  ["Timestamp", "Sender", "Recipient", "Content", "Source"],
    "media":     ["Timestamp", "Sender", "Recipient", "Content", "Source"],
    "locations": ["Timestamp", "Coordinates", "Content", "Source"],
    "apps":      ["Timestamp", "Content", "Source"],
    "cloud":     ["Timestamp", "Content", "Source"],
    "deleted":   ["Timestamp", "Content", "Source"],
}


class DataViewerTab(QWidget):
    """Left tree of evidence categories; right pane shows real DB rows."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._on_select = None
        self._case_id: str | None = None

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

        self._populate_tree()

    # ---------- tree ----------
    def _populate_tree(self) -> None:
        """Rebuild the category tree, showing real row counts per category."""
        self.tree.clear()
        device_label = self._case_id or "No case selected"
        root = QTreeWidgetItem([f"\U0001F4F1  {device_label}"])
        self.tree.addTopLevelItem(root)
        self._items = {}

        counts = self._category_counts()
        for label, key, icon in CATEGORIES:
            n = counts.get(key, 0)
            item = QTreeWidgetItem([f"{icon}  {label}  ({n})"])
            item.setData(0, Qt.UserRole, key)
            root.addChild(item)
            self._items[key] = item
        root.setExpanded(True)

    def _category_counts(self) -> dict[str, int]:
        """Query the DB for per-category counts on the active case."""
        if not self._case_id:
            return {}
        try:
            from sqlalchemy import func, select
            from core.database import Artifact, Case
            with self.ctx.case_manager.db.session() as s:
                case = s.scalar(select(Case).where(Case.case_id == self._case_id))
                if case is None:
                    return {}
                rows = s.execute(
                    select(Artifact.category, func.count(Artifact.id))
                    .where(Artifact.case_id == case.id)
                    .group_by(Artifact.category)
                ).all()
            return {c: n for c, n in rows}
        except Exception as exc:
            self.ctx.log(f"Category counts failed: {exc}", "#FF6B6B")
            return {}

    # ---------- data ----------
    def _category_clicked(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.UserRole)
        if not key or not self._case_id:
            return
        headers, rows = self._fetch_rows(key)
        self.table.set_data(headers, rows)
        self.ctx.log(f"Loaded {key}: {len(rows)} rows", "#00E5FF")

    def _fetch_rows(self, category: str) -> tuple[list[str], list[list[str]]]:
        """Return (headers, rows) from the Artifact table for this category."""
        headers = _HEADERS.get(category, ["Timestamp", "Content", "Source"])
        try:
            from sqlalchemy import select
            from core.database import Artifact, Case
            with self.ctx.case_manager.db.session() as s:
                case = s.scalar(select(Case).where(Case.case_id == self._case_id))
                if case is None:
                    return headers, []
                arts = s.execute(
                    select(Artifact)
                    .where(Artifact.case_id == case.id,
                           Artifact.category == category)
                    .order_by(Artifact.timestamp.desc())
                ).scalars().all()

            out: list[list[str]] = []
            for a in arts:
                ts = a.timestamp.strftime("%Y-%m-%d %H:%M:%S") if a.timestamp else ""
                src = a.source or ""
                if category == "calls":
                    out.append([ts, a.sender or "", a.sender or "", a.recipient or "", src])
                elif category in ("sms", "messages"):
                    out.append([ts, a.sender or "", a.recipient or "",
                                a.content or "", src])
                elif category == "locations":
                    out.append([ts, a.content or "", a.content or "", src])
                elif category in ("apps", "cloud", "deleted"):
                    out.append([ts, a.content or "", src])
                else:
                    out.append([ts, a.sender or "", a.recipient or "",
                                a.content or "", src])
            return headers, out
        except Exception as exc:
            self.ctx.log(f"Row fetch failed: {exc}", "#FF6B6B")
            return headers, []

    def _row_selected(self) -> None:
        row = self.table.selected_row()
        if row is None or self._on_select is None:
            return
        blob = "|".join(str(v) for v in row.values()).encode("utf-8")
        md5 = hashlib.md5(blob).hexdigest()
        sha = hashlib.sha256(blob).hexdigest()
        self._on_select(row, md5, sha)

    def _reload(self) -> None:
        self._populate_tree()
        self.ctx.log("Data viewer refreshed", "#8B949E")

    # ---------- external API ----------
    def set_selection_callback(self, callback) -> None:
        self._on_select = callback

    def set_case(self, case_id: str) -> None:
        self._case_id = case_id
        self.case_label.setText(f"Case: {case_id}")
        self._populate_tree()
        self.ctx.log(f"Viewing case {case_id}", "#8B949E")