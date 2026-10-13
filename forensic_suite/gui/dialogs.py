"""Dialogs: data selection, hash sets, advanced filters."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.acquisition_service import REPO_ROOT  # noqa: F401  (puts the engine on sys.path)
from mobileforensics.acquisition import DATA_ITEMS, LOGICAL_ONLY_ROOT, ROOT_REASON


class DataSelectionDialog(QDialog):
    """'Select the data to be extracted' checklist (Android logical method).

    Items the logical method cannot reach are listed but disabled, with the reason,
    so the examiner sees exactly what will and will not be collected.
    """

    def __init__(self, selected: set[str] | None, rooted: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select the data to be extracted")
        self.setMinimumSize(380, 520)
        lay = QVBoxLayout(self)
        self.all_box = QCheckBox("Select all available data")
        self.all_box.setTristate(True)
        self.all_box.clicked.connect(self._toggle_all)
        lay.addWidget(self.all_box)

        self.list = QListWidget()
        self.keys: list[tuple[QListWidgetItem, str]] = []
        for key, label, _supported in DATA_ITEMS:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if selected is None or key in selected
                               else Qt.Unchecked)
            self.keys.append((item, key))
            self.list.addItem(item)
        for label in LOGICAL_ONLY_ROOT:
            item = QListWidgetItem(f"{label}  (needs file-system method)")
            item.setFlags(Qt.NoItemFlags)
            item.setToolTip(ROOT_REASON)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._sync_all)
        lay.addWidget(self.list, 1)

        note = QLabel("Greyed-out items need the file-system method on a rooted, "
                      "authorized test device." if not rooted else
                      "Greyed-out items are collected by the file-system method.")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self._sync_all()

    def _toggle_all(self) -> None:
        state = Qt.Checked if self.all_box.checkState() != Qt.Unchecked else Qt.Unchecked
        self.list.blockSignals(True)
        for item, _key in self.keys:
            item.setCheckState(state)
        self.list.blockSignals(False)
        self._sync_all()

    def _sync_all(self, *_args) -> None:
        n = sum(1 for i, _k in self.keys if i.checkState() == Qt.Checked)
        self.all_box.blockSignals(True)
        self.all_box.setCheckState(Qt.Checked if n == len(self.keys)
                                   else Qt.Unchecked if n == 0 else Qt.PartiallyChecked)
        self.all_box.blockSignals(False)

    def selection(self) -> set[str]:
        return {k for i, k in self.keys if i.checkState() == Qt.Checked}


class HashSetsDialog(QDialog):
    """Import, list and delete hash sets (known = ignore, notable = alert)."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Hash sets")
        self.setMinimumSize(560, 360)
        lay = QVBoxLayout(self)
        info = QLabel("A hash set is a text/CSV list of MD5 or SHA-256 values. Files that "
                      "match are flagged in the Files view.")
        info.setWordWrap(True)
        info.setProperty("role", "muted")
        lay.addWidget(info)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Kind", "Hashes", "Added"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        add = QPushButton("Import hash set…")
        add.setObjectName("Primary")
        add.clicked.connect(self._import)
        rm = QPushButton("Delete selected")
        rm.setObjectName("Danger")
        rm.clicked.connect(self._delete)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)
        self._sets: list[dict] = []
        self._reload()

    def _reload(self) -> None:
        self._sets = self.ctx.files.list_hash_sets()
        self.table.setRowCount(len(self._sets))
        for r, h in enumerate(self._sets):
            for c, v in enumerate((h["name"], h["kind"], f"{h['entries']:,}", h["added"])):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Hash list", "",
                                              "Hash lists (*.txt *.csv *.hash *.md5 *.sha256);;All files (*)")
        if not path:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Hash set type")
        box.setText("Are these hashes of known files to ignore, or notable files to flag?")
        notable = box.addButton("Notable (flag)", QMessageBox.AcceptRole)
        known = box.addButton("Known (ignore)", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (notable, known):
            return
        from pathlib import Path
        try:
            _id, n = self.ctx.files.import_hash_set(
                Path(path).stem, "notable" if clicked is notable else "known", Path(path))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Hash sets", str(exc))
            return
        self.ctx.notify("Hash sets", f"Imported {n:,} hashes from {Path(path).name}")
        self._reload()

    def _delete(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        h = self._sets[r]
        if QMessageBox.question(self, "Delete", f"Delete hash set '{h['name']}'?") == QMessageBox.Yes:
            self.ctx.files.delete_hash_set(h["id"])
            self._reload()


class AdvancedFiltersDialog(QDialog):
    """Size, date, extension, tag and hash-set filters for the Files view."""

    def __init__(self, current: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced filters")
        form = QFormLayout(self)
        self.ext = QLineEdit(current.get("ext", ""))
        self.ext.setPlaceholderText("e.g. xlsx")
        self.tag = QLineEdit(current.get("tag", ""))
        self.min_kb = QSpinBox()
        self.max_kb = QSpinBox()
        for sp, key in ((self.min_kb, "min_size"), (self.max_kb, "max_size")):
            sp.setRange(0, 2_000_000_000)
            sp.setSuffix(" KB")
            sp.setSpecialValueText("any")
            v = current.get(key)
            sp.setValue(int(v) // 1024 if v is not None else 0)
        self.use_dates = QCheckBox("Filter by modified date")
        self.use_dates.setChecked(bool(current.get("date_from") or current.get("date_to")))
        self.d_from = QDateEdit(QDate.currentDate().addYears(-1))
        self.d_to = QDateEdit(QDate.currentDate())
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
        self.hash_hit = QCheckBox("Only files matching a hash set")
        self.hash_hit.setChecked(bool(current.get("hash_hit")))
        form.addRow("Extension", self.ext)
        form.addRow("Tag contains", self.tag)
        form.addRow("Minimum size", self.min_kb)
        form.addRow("Maximum size", self.max_kb)
        form.addRow(self.use_dates)
        form.addRow("From", self.d_from)
        form.addRow("To", self.d_to)
        form.addRow(self.hash_hit)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Apply")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow(row)

    def values(self) -> dict:
        from datetime import datetime, time
        out: dict = {"ext": self.ext.text().strip(), "tag": self.tag.text().strip(),
                     "hash_hit": self.hash_hit.isChecked()}
        out["min_size"] = self.min_kb.value() * 1024 if self.min_kb.value() else None
        out["max_size"] = self.max_kb.value() * 1024 if self.max_kb.value() else None
        if self.use_dates.isChecked():
            out["date_from"] = datetime.combine(self.d_from.date().toPython(), time.min)
            out["date_to"] = datetime.combine(self.d_to.date().toPython(), time.max)
        return out
