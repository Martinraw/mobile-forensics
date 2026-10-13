"""Case explorer: Cases > extractions > sections (with live counts)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

# key, label, icon
SECTIONS = [
    ("contacts", "Contacts", "\U0001F464"), ("calls", "Calls", "\U0001F4DE"),
    ("messages", "Messages", "\U0001F4AC"), ("calendar", "Calendar", "\U0001F4C5"),
    ("files", "Files", "\U0001F4C1"), ("key", "Key Evidence", "\u2B50"),
    ("timeline", "Timeline", "\U0001F552"), ("apps", "Applications", "\U0001F4E6"),
]


class CaseExplorer(QFrame):
    # kind ("case" | "extraction" | "section"), case_id, extraction_id (or 0), section
    activated = Signal(str, str, int, str)
    reindex_requested = Signal(int)
    deleted = Signal()

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Explorer")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QFrame()
        head.setObjectName("ExplorerHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(10, 6, 6, 6)
        self.title = QLabel("Cases")
        self.title.setStyleSheet("font-weight:700; color:#FFFFFF;")
        hl.addWidget(self.title, 1)
        refresh = QToolButton()
        refresh.setText("\u21BB")
        refresh.setToolTip("Refresh")
        refresh.clicked.connect(self.refresh)
        hl.addWidget(refresh)
        lay.addWidget(head)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._clicked)
        lay.addWidget(self.tree, 1)

        self.find = QLineEdit()
        self.find.setPlaceholderText("Find text\u2026")
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._find)
        lay.addWidget(self.find)

    # ------------------------------------------------------------ build
    def refresh(self) -> None:
        expanded = self._expanded_keys()
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        cases = self.ctx.case_manager.case_tree()
        self.title.setText(f"Cases ({len(cases)})")
        bold = QFont()
        bold.setBold(True)
        for case in cases:
            citem = QTreeWidgetItem([f"\U0001F5C2  {case['case_id']}  \u2014  {case['title']}"])
            citem.setData(0, Qt.UserRole, ("case", case["case_id"], 0, ""))
            if case["case_id"] == self.ctx.current_case:
                citem.setFont(0, bold)
            self.tree.addTopLevelItem(citem)
            for ext in case["extractions"]:
                self._add_extraction(citem, case["case_id"], ext, expanded)
            citem.setExpanded(("case", case["case_id"]) in expanded
                              or case["case_id"] == self.ctx.current_case)
        self.tree.setUpdatesEnabled(True)

    def _add_extraction(self, parent: QTreeWidgetItem, case_id: str, ext: dict,
                        expanded: set) -> None:
        info = ext["info"]
        label = info.get("model") or ext["device"]
        eitem = QTreeWidgetItem([f"\U0001F4F1  {label} \u2014 {ext['method']}"])
        eitem.setData(0, Qt.UserRole, ("extraction", case_id, ext["id"], "overview"))
        eitem.setToolTip(0, f"{ext['started']}\n{ext['out_dir']}")
        parent.addChild(eitem)
        counts = self.ctx.case_manager.artifact_counts(case_id, ext["id"])
        n_files, _size = self.ctx.files.totals(case_id, ext["id"])
        n_key = self.ctx.files.key_evidence_count(case_id, ext["id"])
        values = {"contacts": counts.get("contacts", 0), "calls": counts.get("calls", 0),
                  "messages": counts.get("sms", 0) + counts.get("whatsapp", 0),
                  "calendar": counts.get("calendar", 0), "files": n_files, "key": n_key,
                  "timeline": None, "apps": counts.get("apps", 0)}
        for key, name, icon in SECTIONS:
            n = values[key]
            if n == 0 and key not in ("files", "key"):
                continue
            text = f"{icon}  {name}" + (f"    {n:,}" if n is not None else "")
            sitem = QTreeWidgetItem([text])
            sitem.setData(0, Qt.UserRole, ("section", case_id, ext["id"], key))
            eitem.addChild(sitem)
            if key == "apps" and counts.get("whatsapp"):
                w = QTreeWidgetItem([f"\U0001F7E2  WhatsApp Messenger    {counts['whatsapp']:,}"])
                w.setData(0, Qt.UserRole, ("section", case_id, ext["id"], "whatsapp"))
                sitem.addChild(w)
                sitem.setExpanded(True)
        eitem.setExpanded(("ext", ext["id"]) in expanded
                          or ext["id"] == self.ctx.current_extraction)

    def _expanded_keys(self) -> set:
        keys = set()

        def walk(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.UserRole)
            if data and item.isExpanded():
                if data[0] == "case":
                    keys.add(("case", data[1]))
                elif data[0] == "extraction":
                    keys.add(("ext", data[2]))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return keys

    # ------------------------------------------------------------ events
    def _clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole)
        if data:
            self.activated.emit(*data)

    def _find(self, text: str) -> None:
        term = text.strip().lower()

        def walk(item: QTreeWidgetItem) -> bool:
            child_hit = any([walk(item.child(i)) for i in range(item.childCount())])
            hit = not term or term in item.text(0).lower()
            item.setHidden(not (hit or child_hit))
            if term and (hit or child_hit):
                item.setExpanded(True)
            return hit or child_hit

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        data = item.data(0, Qt.UserRole) if item else None
        if not data:
            return
        menu = QMenu(self)
        kind, case_id, ext_id, _section = data
        if kind == "case":
            menu.addAction("Make active case", lambda: self.activated.emit(*data))
        elif kind in ("extraction", "section"):
            menu.addAction("Open overview", lambda: self.activated.emit(
                "extraction", case_id, ext_id, "overview"))
            menu.addAction("Re-index files and re-parse", lambda: self.reindex_requested.emit(ext_id))
            menu.addSeparator()
            menu.addAction("Remove from case (keeps evidence on disk)",
                           lambda: self._remove(ext_id))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _remove(self, ext_id: int) -> None:
        ok = QMessageBox.question(
            self, "Remove extraction",
            "Remove this extraction's index, parsed data and tags from the case database?\n\n"
            "The evidence files on disk are NOT deleted.")
        if ok == QMessageBox.Yes:
            self.ctx.case_manager.delete_extraction_records(ext_id)
            self.ctx.add_custody(self.ctx.current_case, f"extraction_records_removed id={ext_id}")
            self.refresh()
            self.deleted.emit()
