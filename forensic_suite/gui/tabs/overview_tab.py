"""Extraction overview: device header, detail tabs, section and analytics tiles."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from core.evidence_files import CATEGORIES, human_size
from widgets.tile import Tile


def _value(text: str) -> QLabel:
    lab = QLabel(text or "\u2014")
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lab.setWordWrap(True)
    return lab


class OverviewTab(QWidget):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.ext: dict | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(18, 18, 18, 18)
        self.lay.setSpacing(14)
        scroll.setWidget(body)

        self.heading = QLabel("Select an extraction in the case explorer")
        self.heading.setObjectName("SectionTitle")
        self.lay.addWidget(self.heading)

        # header: icon + key facts
        head = QHBoxLayout()
        self.icon = QLabel("\U0001F4F1")
        self.icon.setStyleSheet("font-size:64px;")
        self.icon.setFixedWidth(100)
        self.icon.setAlignment(Qt.AlignCenter)
        head.addWidget(self.icon)
        self.facts = QFormLayout()
        self.f_tz, self.f_os = QLabel("\u2014"), QLabel("\u2014")
        self.f_incident, self.f_evidence = QLineEdit(), QLineEdit()
        self.f_incident.setPlaceholderText("Add incident number")
        self.f_evidence.setPlaceholderText("Add evidence number")
        for w, key in ((self.f_incident, "incident_number"), (self.f_evidence, "evidence_number")):
            w.setMaximumWidth(260)
            w.editingFinished.connect(lambda w=w, k=key: self._save_field(k, w.text()))
        self.facts.addRow("Time zone", self.f_tz)
        self.facts.addRow("OS", self.f_os)
        self.facts.addRow("Incident number", self.f_incident)
        self.facts.addRow("Evidence number", self.f_evidence)
        head.addLayout(self.facts, 1)
        self.lay.addLayout(head)

        # detail tabs
        self.tabs = QTabWidget()
        self.t_stats, self.t_extr = QWidget(), QWidget()
        self.t_owner, self.t_general = QWidget(), QWidget()
        self.t_device, self.t_photos, self.t_note = QWidget(), QWidget(), QWidget()
        for w, name in ((self.t_stats, "Statistics"), (self.t_extr, "Extraction info"),
                        (self.t_owner, "Owner"), (self.t_general, "General info"),
                        (self.t_device, "Device"), (self.t_photos, "Photos"),
                        (self.t_note, "Note")):
            self.tabs.addTab(w, name)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.setMinimumHeight(230)
        self.lay.addWidget(self.tabs)

        self.sections_box = self._group("General sections")
        self.analytics_box = self._group("Analytics")
        self.apps_box = self._group("Applications")
        self.lay.addStretch()

        # persistent widgets for owner / note tabs
        self.o_name, self.o_phone, self.o_email = QLineEdit(), QLineEdit(), QLineEdit()
        form = QFormLayout(self.t_owner)
        for label, w, key in (("Owner name", self.o_name, "owner_name"),
                              ("Phone number", self.o_phone, "owner_phone"),
                              ("E-mail", self.o_email, "owner_email")):
            w.editingFinished.connect(lambda w=w, k=key: self._save_field(k, w.text()))
            form.addRow(label, w)
        nl = QVBoxLayout(self.t_note)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Examiner notes for this extraction\u2026")
        nl.addWidget(self.note)
        save = QPushButton("Save note")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_note)
        nl.addWidget(save, 0, Qt.AlignRight)

        self.photo_list = QListWidget()
        self.photo_list.setViewMode(QListView.IconMode)
        self.photo_list.setIconSize(QSize(110, 110))
        self.photo_list.setResizeMode(QListView.Adjust)
        self.photo_list.setSpacing(6)
        self.photo_list.itemDoubleClicked.connect(
            lambda _i: self.ctx.open_section("images", self.ext["id"] if self.ext else None))
        pl = QVBoxLayout(self.t_photos)
        pl.addWidget(self.photo_list)
        self._photos_loaded = False

    def _group(self, title: str) -> QGridLayout:
        label = QLabel(title)
        label.setStyleSheet("font-size:15px; font-weight:600; color:#00B8D4;")
        self.lay.addWidget(label)
        host = QFrame()
        host.setObjectName("Card")
        grid = QGridLayout(host)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)
        self.lay.addWidget(host)
        return grid

    # ------------------------------------------------------------ data
    def show_extraction(self, extraction_id: int) -> None:
        ext = self.ctx.case_manager.get_extraction(extraction_id)
        if ext is None:
            return
        self.ext = ext
        info = ext["info"]
        label = f"{info.get('vendor', '').title()} {info.get('model') or ext['device']}".strip()
        self.heading.setText(f"{ext['method'].title()} extraction \u2014 {label}")
        self.icon.setText("\U0001F4F1" if info.get("platform", "Android") != "Imported" else "\U0001F4BE")
        self.f_tz.setText(info.get("timezone") or "\u2014")
        os_name = info.get("platform", "")
        self.f_os.setText(f"{os_name} {info.get('os_version', '')}".strip() or "\u2014")
        for w, k in ((self.f_incident, "incident_number"), (self.f_evidence, "evidence_number"),
                     (self.o_name, "owner_name"), (self.o_phone, "owner_phone"),
                     (self.o_email, "owner_email")):
            w.setText(info.get(k, ""))
        self.note.setPlainText(ext["note"])
        self._fill_extraction_info(ext)
        self._fill_general(ext)
        self._fill_device(ext)
        self._fill_stats(ext)
        self._fill_tiles(ext)
        self._photos_loaded = False
        self.photo_list.clear()
        if self.tabs.currentWidget() is self.t_photos:
            self._load_photos()

    def _replace_layout(self, host: QWidget) -> QFormLayout:
        old = host.layout()
        if old is not None and host not in (self.t_owner, self.t_note, self.t_photos):
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)  # detach so a new layout can be set
        form = QFormLayout(host)
        form.setLabelAlignment(Qt.AlignRight)
        return form

    def _fill_extraction_info(self, ext: dict) -> None:
        form = self._replace_layout(self.t_extr)
        out = Path(ext["out_dir"]) if ext["out_dir"] else None
        manifest = None
        if out is not None:
            for cand in (out.parent / f"{out.name}.manifest.json",
                         out.parent / f"{out.name.removesuffix('_extracted')}.manifest.json"):
                if cand.is_file():
                    manifest = cand
                    break
        sha = ""
        if manifest is not None:
            from mobileforensics.evidence import sha256_file
            sha = sha256_file(manifest)
        rows = [("Case", ext["case"]), ("Method", ext["method"]), ("Status", ext["status"]),
                ("Started", ext["started"]), ("Finished", ext["finished"]),
                ("Files", f"{ext['files']:,}"), ("Size", human_size(ext["size_bytes"])),
                ("Output folder", ext["out_dir"]),
                ("Manifest", str(manifest) if manifest else "\u2014"),
                ("Manifest SHA-256", sha or "\u2014")]
        if ext["info"].get("source"):
            rows.append(("Imported from", ext["info"]["source"]))
            rows.append(("Source SHA-256", ext["info"].get("source_sha256", "") or "\u2014"))
        for k, v in rows:
            form.addRow(f"{k}", _value(str(v)))

    def _fill_general(self, ext: dict) -> None:
        form = self._replace_layout(self.t_general)
        case = self.ctx.case_manager.get_case(ext["case"])
        rows = [("Case ID", ext["case"]), ("Case title", case.title if case else ""),
                ("Examiner", case.examiner if case else ""),
                ("Authorization", case.authorization_ref if case else ""),
                ("Platform", ext["info"].get("platform", "")),
                ("Serial", ext["info"].get("serial", "")), ("IMEI", ext["info"].get("imei", ""))]
        for k, v in rows:
            form.addRow(k, _value(v))

    def _fill_device(self, ext: dict) -> None:
        form = self._replace_layout(self.t_device)
        i = ext["info"]
        rows = [("Device vendor", i.get("vendor", "")), ("Device model", i.get("model", "")),
                ("OS version", i.get("os_version", "")),
                ("Security patch", i.get("security_patch", "")),
                ("Build", i.get("build_id", "")), ("Fingerprint", i.get("fingerprint", "")),
                ("Chipset", i.get("chipset", "")), ("Time zone", i.get("timezone", "")),
                ("SIM country ISO", i.get("sim_country", "")),
                ("SIM operator", i.get("sim_operator", "")),
                ("SIM operator code", i.get("sim_operator_code", "")),
                ("Language", i.get("language", ""))]
        if not any(v for _, v in rows):
            form.addRow(_value("No device properties were collected (select \"Device "
                               "information\" in the data list, or this is an imported image)."))
            return
        for k, v in rows:
            form.addRow(k, _value(v))

    def _fill_stats(self, ext: dict) -> None:
        old = self.t_stats.layout()
        if old is None:
            lay = QVBoxLayout(self.t_stats)
            self.stats_table = QTableWidget(0, 2)
            self.stats_table.setHorizontalHeaderLabels(["Item", "Count"])
            self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.stats_table.verticalHeader().setVisible(False)
            self.stats_table.horizontalHeader().setStretchLastSection(True)
            lay.addWidget(self.stats_table)
        counts = self.ctx.files.category_counts(ext["case"], ext["id"])
        arts = self.ctx.case_manager.artifact_counts(ext["case"], ext["id"])
        rows = [(label, counts.get(key, 0)) for key, label in CATEGORIES]
        rows += [(f"Parsed: {k}", v) for k, v in sorted(arts.items())]
        self.stats_table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.stats_table.setItem(r, 0, QTableWidgetItem(k))
            self.stats_table.setItem(r, 1, QTableWidgetItem(f"{v:,}"))

    def _fill_tiles(self, ext: dict) -> None:
        cid, eid = ext["case"], ext["id"]
        arts = self.ctx.case_manager.artifact_counts(cid, eid)
        n_files, _s = self.ctx.files.totals(cid, eid)
        n_key = self.ctx.files.key_evidence_count(cid, eid)
        hits = len(self.ctx.files.query(cid, eid, hash_hit=True, limit=100000))
        go = self.ctx.open_section

        def fill(grid: QGridLayout, tiles: list[Tile]) -> None:
            while grid.count():
                w = grid.takeAt(0).widget()
                if w:
                    w.deleteLater()
            for i, t in enumerate(tiles):
                grid.addWidget(t, i // 4, i % 4)
            for c in range(4):
                grid.setColumnStretch(c, 1)

        def tile(icon, title, count, section, enabled=True, tip=""):
            t = Tile(icon, title, "items" if count is not None else "", count,
                     enabled=enabled, tooltip=tip)
            t.clicked.connect(lambda s=section: go(s, eid))
            return t

        fill(self.sections_box, [
            tile("\U0001F4C1", "Files", n_files, "files"),
            tile("\U0001F464", "Contacts", arts.get("contacts", 0), "contacts"),
            tile("\U0001F4DE", "Calls", arts.get("calls", 0), "calls"),
            tile("\U0001F4AC", "Messages", arts.get("sms", 0) + arts.get("whatsapp", 0), "messages"),
            tile("\U0001F4C5", "Calendar", arts.get("calendar", 0), "calendar"),
            tile("\U0001F4C4", "Reports", None, "reports")])
        fill(self.analytics_box, [
            tile("\u2B50", "Key Evidence", n_key, "key"),
            tile("\U0001F50D", "Search", None, "search"),
            tile("\U0001F552", "Timeline", None, "timeline"),
            tile("#\uFE0F\u20E3", "Hash set hits", hits, "hashhits",
                 tip="Files matching an imported hash set")])
        apps = [tile("\U0001F4E6", "Installed packages", arts.get("apps", 0), "apps")]
        if arts.get("whatsapp"):
            apps.append(tile("\U0001F7E2", "WhatsApp Messenger", arts["whatsapp"], "whatsapp"))
        fill(self.apps_box, apps)

    # ------------------------------------------------------------ photos
    def _tab_changed(self, _i: int) -> None:
        if self.tabs.currentWidget() is self.t_photos and not self._photos_loaded:
            self._load_photos()

    def _load_photos(self) -> None:
        if not self.ext:
            return
        self._photos_loaded = True
        rows = self.ctx.files.query(self.ext["case"], self.ext["id"], category="images",
                                    order="modified", desc=True, limit=120)
        for r in rows:
            pix = QPixmap(r["abs_path"])
            if pix.isNull():
                continue
            item = QListWidgetItem(QIcon(pix.scaled(110, 110, Qt.KeepAspectRatio,
                                                    Qt.SmoothTransformation)), "")
            item.setToolTip(r["device_path"])
            self.photo_list.addItem(item)

    # ------------------------------------------------------------ editing
    def _save_field(self, key: str, value: str) -> None:
        if self.ext:
            self.ctx.case_manager.update_extraction_info(self.ext["id"], **{key: value.strip()})
            self.ctx.add_custody(self.ctx.current_case, f"extraction_{key}_updated")

    def _save_note(self) -> None:
        if self.ext:
            self.ctx.case_manager.set_extraction_note(self.ext["id"], self.note.toPlainText())
            self.ctx.notify("Note", "Saved")
