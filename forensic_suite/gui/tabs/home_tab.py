"""Home: Extract / Common tasks / Import launcher."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from widgets.tile import Tile

# (group title, icon, [(link label, import kind)])
IMPORT_GROUPS = [
    ("Android", "\U0001F916", [
        ("File system tarball / zip", "archive"), ("File system folder", "folder"),
        ("Physical / JTAG image", "image"), ("ADB backup", "image"),
        ("TWRP / CWM backup", "image"), ("Samsung Smart Switch backup", "folder")]),
    ("Apple", "\U0001F34E", [
        ("iTunes / Finder backup folder", "folder"), ("File system tarball / zip", "archive"),
        ("File system folder", "folder")]),
    ("Memory cards / MTP", "\U0001F4BE", [
        ("Physical image", "image"), ("File system tarball / zip", "archive"),
        ("File system folder", "folder")]),
    ("Application data", "\U0001F4AC", [
        ("WhatsApp msgstore.db (decrypted)", "whatsapp")]),
]
NOT_AVAILABLE = ("Cloud acquisition and exploit-based physical extraction are out of scope "
                 "for this tool (see docs/DESIGN.md).")


class HomeTab(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(40, 24, 40, 24)
        lay.setSpacing(12)
        scroll.setWidget(body)

        self._section(lay, "Extract")
        grid = QGridLayout()
        grid.setSpacing(12)
        t1 = Tile("\U0001F4F1", "Device Extractor", "Acquire data from a connected Android or iPhone")
        t1.clicked.connect(lambda: ctx.navigate("extraction"))
        t2 = Tile("\u2601\uFE0F", "Cloud Extractor", "Not available in this tool",
                  enabled=False, tooltip=NOT_AVAILABLE)
        grid.addWidget(t1, 0, 0)
        grid.addWidget(t2, 0, 1)
        lay.addLayout(grid)

        self._section(lay, "Common tasks")
        grid = QGridLayout()
        grid.setSpacing(12)
        t3 = Tile("\U0001F4C1", "New case", "Add a new case with its authorization reference")
        t3.clicked.connect(lambda: ctx.show_new_case_dialog())
        t4 = Tile("\U0001F4E5", "Backup import", "Import a device backup, image or folder")
        t4.clicked.connect(lambda: ctx.import_evidence("any"))
        grid.addWidget(t3, 0, 0)
        grid.addWidget(t4, 0, 1)
        lay.addLayout(grid)

        self._section(lay, "Import")
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (title, icon, links) in enumerate(IMPORT_GROUPS):
            grid.addWidget(self._group(title, icon, links), i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        note = QLabel("Imported files are copied into the case, hash-verified and audited. Zip and "
                      "tar archives are extracted safely and indexed. Raw disk images are stored "
                      "and hashed but cannot be opened yet (see README, phase 5).")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        lay.addWidget(note)

        self._section(lay, "Recent extractions")
        self.recent = QVBoxLayout()
        lay.addLayout(self.recent)
        lay.addStretch()

    @staticmethod
    def _section(lay: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet("font-size:18px; font-weight:600; border-bottom:1px solid #30363D; "
                            "padding-bottom:4px; margin-top:10px;")
        lay.addWidget(label)

    def _group(self, title: str, icon: str, links: list[tuple[str, str]]) -> QWidget:
        box = QFrame()
        box.setObjectName("Tile")
        hl = QHBoxLayout(box)
        hl.setContentsMargins(12, 10, 12, 10)
        ic = QLabel(icon)
        ic.setStyleSheet("font-size:32px; background:transparent;")
        ic.setAlignment(Qt.AlignTop)
        hl.addWidget(ic)
        col = QVBoxLayout()
        head = QLabel(title)
        head.setStyleSheet("font-size:15px; font-weight:600; color:#E6EDF3; background:transparent;")
        col.addWidget(head)
        for label, kind in links:
            b = QPushButton(label)
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-align:left; color:#3AA6FF; border:none; padding:1px 0;")
            b.clicked.connect(lambda _=False, k=kind: self.ctx.import_evidence(k))
            col.addWidget(b, 0, Qt.AlignLeft)
        col.addStretch()
        hl.addLayout(col, 1)
        hl.setAlignment(ic, Qt.AlignTop)
        return box

    def refresh(self) -> None:
        while self.recent.count():
            w = self.recent.takeAt(0).widget()
            if w:
                w.deleteLater()
        rows = self.ctx.case_manager.list_extractions()[:6]
        if not rows:
            msg = QLabel("Nothing yet. Create a case, then extract from a device or import evidence.")
            msg.setProperty("role", "muted")
            self.recent.addWidget(msg)
            return
        for e in rows:
            label = e["info"].get("model") or e["device"]
            b = QPushButton(f"\U0001F4F1  {label} \u2014 {e['method']}   \u00b7   case {e['case']}   "
                            f"\u00b7   {e['started']}")
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-align:left; color:#3AA6FF; border:none; padding:2px 0;")
            b.clicked.connect(lambda _=False, i=e["id"]: self.ctx.open_extraction(i))
            self.recent.addWidget(b, 0, Qt.AlignLeft)
