"""Sortable, searchable data table with CSV export."""
from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)


class DataTable(QWidget):
    """A rich table widget: sortable columns, quick filter, CSV export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter rows\u2026")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(280)
        self.search_box.textChanged.connect(self.apply_filter)
        self.count_label = QLabel("0 rows")
        self.count_label.setProperty("role", "muted")
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("Ghost")
        self.export_btn.clicked.connect(self.export_current)
        toolbar.addWidget(self.search_box)
        toolbar.addWidget(self.count_label)
        toolbar.addStretch()
        toolbar.addWidget(self.export_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 0)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.table, 1)

        self._all_rows: list[list[str]] = []

    def clear(self) -> None:
        self.table.setRowCount(0)
        self._all_rows = []
        self.count_label.setText("0 rows")

    def set_data(self, headers: list[str], rows: list[list]) -> None:
        self._all_rows = [["" if v is None else str(v) for v in row] for row in rows]
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.apply_filter("")
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def apply_filter(self, text: str) -> None:
        term = text.strip().lower()
        filtered = [r for r in self._all_rows if not term or any(term in c.lower() for c in r)]
        self.table.setRowCount(len(filtered))
        for row, values in enumerate(filtered):
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 0:
                    item.setData(Qt.UserRole, value)
                self.table.setItem(row, col, item)
        self.count_label.setText(f"{len(filtered)} row{'s' if len(filtered) != 1 else ''}")

    def export_current(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export artifacts",
                                              "artifacts.csv", "CSV files (*.csv)")
        if not path:
            return
        headers = [self.table.horizontalHeaderItem(c).text()
                   for c in range(self.table.columnCount())]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in range(self.table.rowCount()):
                writer.writerow([self.table.item(row, c).text() if self.table.item(row, c)
                                 else "" for c in range(self.table.columnCount())])
        QMessageBox.information(self, "Export",
                                f"Exported {self.table.rowCount()} rows to\n{path}")

    def selected_row(self) -> dict | None:
        """Return the currently selected row as {header: value} or None."""
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not indexes:
            return None
        row = indexes[0].row()
        return {self.table.horizontalHeaderItem(c).text()
                if self.table.horizontalHeaderItem(c) else str(c):
                    self.table.item(row, c).text() if self.table.item(row, c) else ""
                for c in range(self.table.columnCount())}