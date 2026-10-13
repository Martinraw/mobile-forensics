"""Files: folder tree, category tabs, filterable table, key evidence, tags,
details/preview panel, duplicates and hash-set flags."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabBar,
                               QTableView, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from core.evidence_files import CATEGORIES, PRESET_TAGS, human_size
from gui.dialogs import AdvancedFiltersDialog, HashSetsDialog

COLS = ["", "\u2605", "Tag", "Name", "Created", "Modified", "Type", "Size", "Dup",
        "Hash set", "Full path"]
SORT_KEYS = {1: "key", 2: "tag", 3: "name", 4: "created", 5: "modified", 6: "type",
             7: "size", 10: "path"}
TEXT_EXT = {"txt", "json", "csv", "xml", "log", "md", "html", "htm", "vcf", "ics", "jsonl"}
FMT = "%Y-%m-%d %H:%M:%S"


class FileModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self.checked: set[int] = set()

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.checked &= {r["id"] for r in rows}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLS[section]
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return base | Qt.ItemIsUserCheckable if index.column() == 0 else base

    def data(self, index, role=Qt.DisplayRole):
        r, c = self.rows[index.row()], index.column()
        if c == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if r["id"] in self.checked else Qt.Unchecked
        if role == Qt.DisplayRole:
            return {
                1: "\u2605" if r["key"] else "\u2606", 2: ", ".join(r["tags"]),
                3: r["name"], 4: r["created"].strftime(FMT) if r["created"] else "",
                5: r["modified"].strftime(FMT) if r["modified"] else "",
                6: f'{r["category"].rstrip("s").title()} file "{r["ext"].upper()}"'
                if r["ext"] else r["category"].title(),
                7: human_size(r["size"]), 8: str(r["dups"]) if r["dups"] else "",
                9: r["hashset"], 10: r["device_path"]}.get(c)
        if role == Qt.ForegroundRole:
            if c == 1:
                return QColor("#FFC107" if r["key"] else "#6E7681")
            if r["hashset"] and "(known)" not in r["hashset"]:
                return QColor("#FF6B6B")
        if role == Qt.TextAlignmentRole and c in (1, 7, 8):
            return int(Qt.AlignRight | Qt.AlignVCenter) if c != 1 else int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return r["device_path"]
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0 and role == Qt.CheckStateRole:
            fid = self.rows[index.row()]["id"]
            (self.checked.add if value in (Qt.Checked, 2) else self.checked.discard)(fid)
            self.dataChanged.emit(index, index, [role])
            return True
        return False


class FilesTab(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.case_id: str | None = None
        self.extraction_id: int | None = None
        self.category = "all"
        self.folder = ""
        self.key_only = False
        self.adv: dict = {}
        self.order, self.desc = "name", False
        self._counts_busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- toolbar ----
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 8)
        self.title = QLabel("\U0001F4C1  Files")
        self.title.setObjectName("SectionTitle")
        bar.addWidget(self.title)
        bar.addStretch()
        for text, slot, tip in (
                ("Export \u25BE", self._export_menu, "Export the view or copy files out"),
                ("Reset filters", self.reset_filters, "Clear every filter"),
                ("Key evidence", self._toggle_key_only, "Show only key evidence"),
                ("Hash sets", self._hash_sets, "Manage known / notable hash sets"),
                ("Advanced filters", self._advanced, "Size, date, extension, tag"),
                ("Re-index", self._reindex, "Re-hash and re-parse this extraction")):
            b = QPushButton(text)
            b.setObjectName("Ghost")
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
            if text == "Key evidence":
                self.key_btn = b
                b.setCheckable(True)
            if text.startswith("Export"):
                self.export_btn = b
        root.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # ---- folder tree ----
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Folders")
        self.tree.itemSelectionChanged.connect(self._folder_changed)
        split.addWidget(self.tree)

        # ---- centre ----
        centre = QWidget()
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        self.tabbar = QTabBar()
        self.tabbar.setObjectName("CategoryTabs")
        self.tabbar.setExpanding(False)
        self.tabbar.setUsesScrollButtons(True)
        for key, label in CATEGORIES:
            self.tabbar.addTab(label)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter: name, path, tag, note, hash\u2026")
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        cl.addWidget(self.search)
        cl.addWidget(self.tabbar)

        self.model = FileModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(26)
        self.view.setShowGrid(False)
        self.view.setWordWrap(False)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)
        hdr = self.view.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.sectionClicked.connect(self._header_clicked)
        for c, w in enumerate((30, 30, 90, 260, 150, 150, 130, 80, 40, 130, 400)):
            self.view.setColumnWidth(c, w)
        self.view.clicked.connect(self._cell_clicked)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)
        cl.addWidget(self.view, 1)

        self.dups = QTableWidget(0, 4)
        self.dups.setHorizontalHeaderLabels(["Name", "Modified", "Size", "Full path"])
        self.dups.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dups.verticalHeader().setVisible(False)
        self.dups.horizontalHeader().setStretchLastSection(True)
        self.dups.setMaximumHeight(130)
        self.dups_title = QLabel("Duplicates (0)")
        self.dups_title.setProperty("role", "muted")
        cl.addWidget(self.dups_title)
        cl.addWidget(self.dups)
        split.addWidget(centre)

        # ---- details ----
        split.addWidget(self._build_details())
        split.setSizes([230, 760, 330])
        split.setStretchFactor(1, 1)

        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        self.status.setContentsMargins(12, 4, 12, 6)
        root.addWidget(self.status)
        self.model.dataChanged.connect(lambda *_: self._update_status())

        self._current: dict | None = None

    # ------------------------------------------------------------ details panel
    def _build_details(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.d_name = QLabel("Select a file")
        self.d_name.setObjectName("CardTitle")
        self.d_name.setWordWrap(True)
        self.d_name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.d_name)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(150)
        self.preview.setWordWrap(True)
        self.preview.setObjectName("Card")
        lay.addWidget(self.preview)
        row = QHBoxLayout()
        self.b_key = QPushButton("\u2605 Key evidence")
        self.b_key.clicked.connect(self._toggle_key_selected)
        self.b_tag = QPushButton("Tag")
        self.b_tag.clicked.connect(lambda: self._tag_menu(self.b_tag))
        self.b_note = QPushButton("Note")
        self.b_note.clicked.connect(self._edit_note)
        self.b_key.setToolTip("Mark / unmark as key evidence")
        self.b_tag.setToolTip("Add or remove a tag")
        self.b_note.setToolTip("Edit the examiner note")
        for b in (self.b_key, self.b_tag, self.b_note):
            b.setObjectName("Ghost")
            b.setMinimumWidth(0)
            row.addWidget(b)
        lay.addLayout(row)
        self.d_tags = QLabel("")
        self.d_tags.setWordWrap(True)
        self.d_tags.setStyleSheet("color:#FFAB00;")
        lay.addWidget(self.d_tags)
        self.d_fields = QLabel("")
        self.d_fields.setWordWrap(True)
        self.d_fields.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.d_fields.setTextFormat(Qt.RichText)
        lay.addWidget(self.d_fields)
        self.d_long: dict[str, QLineEdit] = {}
        for key in ("Full path", "SHA-256", "MD5"):
            cap = QLabel(key)
            cap.setStyleSheet("font-weight:600;")
            box = QLineEdit()
            box.setReadOnly(True)
            box.setCursorPosition(0)
            self.d_long[key] = box
            lay.addWidget(cap)
            lay.addWidget(box)
        self.d_meta_title = QLabel("Metadata")
        self.d_meta_title.setStyleSheet("background:#0E3A5F; color:#E6EDF3; padding:4px 8px; "
                                        "font-weight:600;")
        lay.addWidget(self.d_meta_title)
        self.d_meta = QLabel("")
        self.d_meta.setWordWrap(True)
        self.d_meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.d_meta)
        lay.addStretch()
        scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(260)
        return scroll

    # ------------------------------------------------------------ public API
    def set_scope(self, case_id: str | None, extraction_id: int | None,
                  category: str | None = None, key_only: bool | None = None) -> None:
        changed = (case_id, extraction_id) != (self.case_id, self.extraction_id)
        self.case_id, self.extraction_id = case_id, extraction_id
        if changed:
            self.folder = ""
            self.adv = {}
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        if category is not None:
            self.category = category
            self.tabbar.blockSignals(True)
            self.tabbar.setCurrentIndex([k for k, _ in CATEGORIES].index(category))
            self.tabbar.blockSignals(False)
        if key_only is not None:
            self.key_only = key_only
            self.key_btn.setChecked(key_only)
        label = f"extraction #{extraction_id}" if extraction_id else f"case {case_id or '\u2014'}"
        self.title.setText(f"\U0001F4C1  Files \u2014 {label}")
        self.rebuild_tree()
        self.reload()

    def _filters(self) -> dict:
        flt = {"category": self.category, "folder": self.folder,
               "text": self.search.text(), "key_only": self.key_only}
        flt.update({k: v for k, v in self.adv.items() if v not in (None, "", False)})
        return flt

    # ------------------------------------------------------------ loading
    def rebuild_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        counts = self.ctx.files.folder_counts(self.case_id, self.extraction_id)
        root = QTreeWidgetItem([f"All files  ({counts.get('', 0):,})"])
        root.setData(0, Qt.UserRole, "")
        self.tree.addTopLevelItem(root)
        nodes = {"": root}
        for path in sorted(k for k in counts if k):
            parent, _, name = path.rpartition("/")
            item = QTreeWidgetItem([f"{name}  ({counts[path]:,})"])
            item.setData(0, Qt.UserRole, path)
            nodes.get(parent, root).addChild(item)
            nodes[path] = item
        root.setExpanded(True)
        for top in range(root.childCount()):
            root.child(top).setExpanded(root.child(top).childCount() < 6)
        sel = nodes.get(self.folder, root)
        sel.setSelected(True)
        self.tree.blockSignals(False)

    def reload(self) -> None:
        flt = self._filters()
        rows = self.ctx.files.query(self.case_id, self.extraction_id, order=self.order,
                                    desc=self.desc, **flt)
        self.model.set_rows(rows)
        counts = self.ctx.files.category_counts(self.case_id, self.extraction_id, **flt)
        self.tabbar.blockSignals(True)
        for i, (key, label) in enumerate(CATEGORIES):
            self.tabbar.setTabText(i, f"{label} ({counts.get(key, 0):,})")
        self.tabbar.blockSignals(False)
        self._clear_details()
        self._update_status()

    def _update_status(self) -> None:
        total, size = self.ctx.files.totals(self.case_id, self.extraction_id)
        sel = len(self.view.selectionModel().selectedRows()) if self.view.selectionModel() else 0
        shown = sum(r["size"] for r in self.model.rows)
        self.status.setText(
            f"Total: {total:,} files ({human_size(size)})    Filtered: {len(self.model.rows):,} "
            f"files ({human_size(shown)})    Selected: {sel:,}    "
            f"Checked: {len(self.model.checked):,}")

    # ------------------------------------------------------------ interactions
    def _tab_changed(self, index: int) -> None:
        self.category = CATEGORIES[index][0]
        self.reload()

    def _folder_changed(self) -> None:
        items = self.tree.selectedItems()
        if items:
            self.folder = items[0].data(0, Qt.UserRole) or ""
            self.reload()

    def _header_clicked(self, col: int) -> None:
        key = SORT_KEYS.get(col)
        if key is None:
            return
        self.desc = (not self.desc) if key == self.order else False
        self.order = key
        self.reload()

    def reset_filters(self) -> None:
        self.adv, self.folder, self.category, self.key_only = {}, "", "all", False
        self.key_btn.setChecked(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.tabbar.blockSignals(True)
        self.tabbar.setCurrentIndex(0)
        self.tabbar.blockSignals(False)
        self.rebuild_tree()
        self.reload()

    def _toggle_key_only(self) -> None:
        self.key_only = self.key_btn.isChecked()
        self.reload()

    def _advanced(self) -> None:
        dlg = AdvancedFiltersDialog(self.adv, self)
        if dlg.exec():
            self.adv = dlg.values()
            self.reload()

    def _hash_sets(self) -> None:
        HashSetsDialog(self.ctx, self).exec()
        self.reload()

    def _reindex(self) -> None:
        if self.extraction_id is None:
            self.ctx.notify("Files", "Open an extraction from the case explorer first.")
            return
        ext = self.ctx.case_manager.get_extraction(self.extraction_id)
        if ext and ext["out_dir"]:
            self.ctx.process_extraction(ext["case"], self.extraction_id, ext["out_dir"])

    def _selected_rows(self) -> list[dict]:
        sm = self.view.selectionModel()
        return [self.model.rows[i.row()] for i in sm.selectedRows()] if sm else []

    def _targets(self) -> list[dict]:
        """Checked rows if any, otherwise the selected rows."""
        if self.model.checked:
            return [r for r in self.model.rows if r["id"] in self.model.checked]
        return self._selected_rows()

    def _cell_clicked(self, index: QModelIndex) -> None:
        if index.column() == 1:
            row = self.model.rows[index.row()]
            self.ctx.files.set_key_evidence([row["id"]], not row["key"])
            self._after_mutation(row["id"])

    def _toggle_key_selected(self) -> None:
        rows = self._targets()
        if not rows:
            return
        new = not all(r["key"] for r in rows)
        self.ctx.files.set_key_evidence([r["id"] for r in rows], new)
        self._after_mutation(rows[0]["id"])
        self.ctx.add_custody(self.ctx.current_case,
                             f"key_evidence {'set' if new else 'cleared'} on {len(rows)} file(s)")

    def _after_mutation(self, keep_id: int | None = None) -> None:
        checked = set(self.model.checked)
        self.reload()
        self.model.checked = checked & {r["id"] for r in self.model.rows}
        self.ctx.refresh_explorer()
        if keep_id is not None:
            for i, r in enumerate(self.model.rows):
                if r["id"] == keep_id:
                    self.view.selectRow(i)
                    break

    def _tag_menu(self, anchor: QWidget) -> None:
        rows = self._targets()
        if not rows:
            return
        menu = QMenu(self)
        for tag in PRESET_TAGS:
            menu.addAction(tag, lambda t=tag: self._apply_tag(rows, t))
        menu.addAction("Custom\u2026", lambda: self._custom_tag(rows))
        existing = sorted({t for r in rows for t in r["tags"]})
        if existing:
            sub = menu.addMenu("Remove tag")
            for t in existing:
                sub.addAction(t, lambda t=t: self._remove_tag(rows, t))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _apply_tag(self, rows: list[dict], tag: str) -> None:
        self.ctx.files.add_tag([r["id"] for r in rows], tag)
        self._after_mutation(rows[0]["id"])

    def _remove_tag(self, rows: list[dict], tag: str) -> None:
        self.ctx.files.remove_tag([r["id"] for r in rows], tag)
        self._after_mutation(rows[0]["id"])

    def _custom_tag(self, rows: list[dict]) -> None:
        text, ok = QInputDialog.getText(self, "Add tag", "Tag:")
        if ok and text.strip():
            self._apply_tag(rows, text.strip())

    def _edit_note(self) -> None:
        if not self._current:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Note", self._current["name"],
                                                 self._current["note"])
        if ok:
            self.ctx.files.set_note(self._current["id"], text)
            self._after_mutation(self._current["id"])

    def _context_menu(self, pos) -> None:
        rows = self._targets()
        if not rows:
            return
        menu = QMenu(self)
        menu.addAction("Toggle key evidence", self._toggle_key_selected)
        tag = menu.addMenu("Tag")
        for t in PRESET_TAGS:
            tag.addAction(t, lambda t=t: self._apply_tag(rows, t))
        tag.addAction("Custom\u2026", lambda: self._custom_tag(rows))
        menu.addSeparator()
        menu.addAction("Copy SHA-256", lambda: QGuiApplication.clipboard().setText(rows[0]["sha256"]))
        menu.addAction("Copy path", lambda: QGuiApplication.clipboard().setText(rows[0]["device_path"]))
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ details
    def _clear_details(self) -> None:
        self._current = None
        self.d_name.setText("Select a file")
        self.preview.clear()
        self.d_tags.clear()
        self.d_fields.clear()
        for box in self.d_long.values():
            box.clear()
        self.d_meta.clear()
        self.dups.setRowCount(0)
        self.dups_title.setText("Duplicates (0)")

    def _selection_changed(self, *_args) -> None:
        self._update_status()
        rows = self._selected_rows()
        if not rows:
            return
        r = rows[0]
        self._current = r
        self.d_name.setText(r["name"])
        self.b_key.setText("\u2605 Key evidence" if not r["key"] else "\u2605 Unmark")
        self.d_tags.setText("Tags: " + ", ".join(r["tags"]) if r["tags"] else "")
        self._show_preview(r)
        fmt = lambda d: d.strftime(FMT) if d else "\u2014"  # noqa: E731
        fields = [("Created", fmt(r["created"])), ("Modified", fmt(r["modified"])),
                  ("Accessed", fmt(r["accessed"])), ("Category", r["category"].title()),
                  ("Size", f'{human_size(r["size"])} ({r["size"]:,} b)')]
        for key, val in (("Full path", r["device_path"]), ("SHA-256", r["sha256"]),
                         ("MD5", r["md5"])):
            self.d_long[key].setText(val)
            self.d_long[key].setCursorPosition(0)
        if r["hashset"]:
            fields.append(("Hash set", r["hashset"]))
        if r["note"]:
            fields.append(("Note", r["note"]))
        self.d_fields.setText("<br>".join(
            f"<b>{k}</b>&nbsp;&nbsp;{self._esc(str(v))}" for k, v in fields))
        self.d_meta.setText(self._metadata(r))
        dups = self.ctx.files.duplicates_of(r["id"])
        self.dups_title.setText(f"Duplicates ({len(dups)})")
        self.dups.setRowCount(len(dups))
        for i, d in enumerate(dups):
            vals = (d["name"], d["modified"].strftime(FMT) if d["modified"] else "",
                    human_size(d["size"]), d["device_path"])
            for c, v in enumerate(vals):
                self.dups.setItem(i, c, QTableWidgetItem(v))
        self.dups.resizeColumnsToContents()

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _show_preview(self, r: dict) -> None:
        self.preview.clear()
        path = Path(r["abs_path"])
        try:
            if r["category"] == "images":
                pix = QPixmap(str(path))
                if not pix.isNull():
                    self.preview.setPixmap(pix.scaled(280, 220, Qt.KeepAspectRatio,
                                                      Qt.SmoothTransformation))
                    return
            if r["ext"] in TEXT_EXT and path.is_file():
                with open(path, "rb") as f:
                    snippet = f.read(1500).decode("utf-8", errors="replace")
                self.preview.setText(self._esc(snippet))
                self.preview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                self.preview.setStyleSheet("font-family:monospace; font-size:11px;")
                return
        except OSError:
            pass
        self.preview.setStyleSheet("")
        self.preview.setAlignment(Qt.AlignCenter)
        icon = {"images": "\U0001F5BC", "audios": "\U0001F3B5", "videos": "\U0001F3AC",
                "documents": "\U0001F4C4", "databases": "\U0001F5C4", "archives": "\U0001F4E6",
                "applications": "\U0001F4F1"}.get(r["category"], "\U0001F4C3")
        self.preview.setText(f'<span style="font-size:48px">{icon}</span>')

    def _metadata(self, r: dict) -> str:
        lines = [f"MIME: {r['mime'] or 'unknown'}"]
        if r["category"] == "images":
            try:
                from PIL import ExifTags, Image
                with Image.open(r["abs_path"]) as im:
                    lines.append(f"Dimensions: {im.width} \u00d7 {im.height}")
                    exif = im.getexif()
                    for tag_id, val in list(exif.items())[:12]:
                        lines.append(f"{ExifTags.TAGS.get(tag_id, tag_id)}: {str(val)[:60]}")
            except Exception:
                pass
        return "\n".join(lines)

    # ------------------------------------------------------------ export
    def _export_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Export this view to CSV\u2026", self._export_csv)
        menu.addAction("Copy checked / selected files to a folder\u2026", self._copy_files)
        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft()))

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export file list", "files.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Key evidence", "Tags", "Name", "Created", "Modified", "Category",
                        "Size", "Full path", "SHA-256", "MD5", "Hash set", "Note"])
            for r in self.model.rows:
                w.writerow(["yes" if r["key"] else "", ";".join(r["tags"]), r["name"],
                            r["created"] or "", r["modified"] or "", r["category"], r["size"],
                            r["device_path"], r["sha256"], r["md5"], r["hashset"], r["note"]])
        self.ctx.notify("Export", f"{len(self.model.rows):,} rows written to {Path(path).name}")

    def _copy_files(self) -> None:
        rows = self._targets()
        if not rows:
            self.ctx.notify("Export", "Check or select files first.")
            return
        dest = QFileDialog.getExistingDirectory(self, "Copy files to")
        if not dest:
            return
        done = bad = 0
        for r in rows:
            target = Path(dest) / r["name"]
            n = 1
            while target.exists():
                n += 1
                target = Path(dest) / f"{Path(r['name']).stem}_{n}{Path(r['name']).suffix}"
            try:
                shutil.copy2(r["abs_path"], target)
                done += 1
            except OSError:
                bad += 1
        self.ctx.add_custody(self.ctx.current_case, f"files_exported count={done} to={dest}")
        QMessageBox.information(self, "Export", f"Copied {done} file(s)"
                                + (f", {bad} failed." if bad else "."))
