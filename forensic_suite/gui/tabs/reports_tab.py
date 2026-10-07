"""Reports: template gallery, section builder, preview and multi-format export."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)

TEMPLATES = ["Case Summary", "Standard HTML Report", "Digital Evidence Brief"]

SECTIONS = [
    ("Case header", "case_header"),
    ("Acquisition details", "acquisition"),
    ("Artifact statistics", "stats"),
    ("Timeline excerpt", "timeline"),
    ("Key findings", "findings"),
    ("Chain of custody", "custody"),
    ("Hash inventory", "hashes"),
    ("Examiner notes", "notes"),
]


class ReportsTab(QWidget):
    """Build and export a case report in HTML / PDF / CSV / JSON / XML."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        heading = QLabel("\U0001F4C4  Reports")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        self.template_list = QListWidget()
        for name in TEMPLATES:
            self.template_list.addItem(name)
        self.template_list.setCurrentRow(0)
        left_lay.addWidget(QLabel("Template gallery"))
        left_lay.addWidget(self.template_list)
        self.section_list = QListWidget()
        for name, key in SECTIONS:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, key)
            self.section_list.addItem(item)
        left_lay.addWidget(QLabel("Sections (click to toggle)"))
        left_lay.addWidget(self.section_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        right_lay.addWidget(QLabel("Preview"))
        right_lay.addWidget(self.preview, 1)

        buttons = QHBoxLayout()
        generate = QPushButton("Generate preview")
        generate.setObjectName("Primary")
        generate.clicked.connect(self._generate)
        buttons.addWidget(generate)
        buttons.addStretch()
        for label, kind in (("PDF", "pdf"), ("HTML", "html"), ("CSV", "csv"),
                            ("JSON", "json"), ("XML", "xml")):
            btn = QPushButton(label)
            btn.setObjectName("Ghost")
            btn.clicked.connect(lambda _=False, k=kind: self._export(k))
            buttons.addWidget(btn)
        right_lay.addLayout(buttons)
        splitter.addWidget(right)
        splitter.setSizes([280, 720])
        layout.addWidget(splitter, 1)

        sched = QLabel(
            "\U0001F552  Scheduled reports: \u201CDaily at 09:00 \u2014 case "
            "DEMO001\u201D (takes effect when the scheduler is enabled in Settings).")
        sched.setProperty("role", "muted")
        layout.addWidget(sched)

        self._generate()

    def _generate(self) -> None:
        self.preview.setHtml(self._build_html())

    def _build_html(self) -> str:
        case = self.ctx.current_case or "\u2014"
        stats = self.ctx.case_manager.stats()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        category_rows = "".join(
            f"<tr><td>{key}</td><td>{value}</td></tr>"
            for key, value in stats["categories"].items())
        parts = [
            "<html><head><style>",
            "body{font-family:'Segoe UI',sans-serif;background:#0D1117;color:#E6EDF3;}",
            "h1{color:#00E5FF;} h2{color:#7C4DFF;border-bottom:1px solid #30363D;}",
            "table{border-collapse:collapse;width:100%;}",
            "td,th{border:1px solid #30363D;padding:6px 10px;text-align:left;}",
            "code{font-family:Consolas,monospace;color:#00E5FF;}",
            "</style></head><body>",
            f"<h1>Mobile Forensic Case Report \u2014 {case}</h1>",
            f"<p>Generated: {now} \u00b7 Framework v0.1.0</p>",
        ]
        for i in range(self.section_list.count()):
            item = self.section_list.item(i)
            if item.checkState() != Qt.Checked:
                continue
            parts.append(self._section_html(item.data(Qt.UserRole),
                                            case, stats, category_rows))
        parts.append("</body></html>")
        return "\n".join(parts)

    def _section_html(self, key: str, case: str, stats: dict,
                      category_rows: str) -> str:
        if key == "case_header":
            return (f"<h2>Case header</h2><table><tr><td><b>Case ID</b></td>"
                    f"<td>{case}</td></tr><tr><td><b>Examiner</b></td>"
                    f"<td>analyst</td></tr><tr><td><b>Status</b></td>"
                    f"<td>Under examination</td></tr></table>")
        if key == "acquisition":
            return (f"<h2>Acquisition details</h2><p>Devices extracted: "
                    f"{stats['devices']} \u00b7 Data volume: {stats['data_gb']} GB "
                    f"\u00b7 Methods: Logical, File-system, Backup (simulated).</p>")
        if key == "stats":
            rows = category_rows or "<tr><td>No data</td><td>0</td></tr>"
            return (f"<h2>Artifact statistics</h2><table><tr><th>Category</th>"
                    f"<th>Count</th></tr>{rows}</table>"
                    f"<p>Total artifacts parsed and indexed.</p>")
        if key == "timeline":
            return ("<h2>Timeline excerpt</h2><p>Interactive timeline available "
                    "in-app. Key window: 2024-02-01 \u2013 2024-02-05.</p>")
        if key == "findings":
            return ("<h2>Key findings</h2><ul><li>Recovered deleted messages "
                    "from WAL journal.</li><li>Two location pings near the "
                    "incident site.</li></ul>")
        if key == "custody":
            return ("<h2>Chain of custody</h2><p>Every action was appended to the "
                    "tamper-evident audit log (SHA-256 chained).</p>")
        if key == "hashes":
            return ("<h2>Hash inventory</h2><p>All acquisition manifests verified "
                    "with SHA-256; copy values from the Inspector panel.</p>")
        return f"<h2>Examiner notes</h2><p>Add conclusions here.</p>"

    def _export(self, kind: str) -> None:
        filters = {"pdf": "PDF files (*.pdf)", "html": "HTML files (*.html)",
                   "csv": "CSV files (*.csv)", "json": "JSON files (*.json)",
                   "xml": "XML files (*.xml)"}
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {kind.upper()}",
            f"report_{self.ctx.current_case}.{kind}", filters[kind])
        if not path:
            return
        try:
            if kind == "html":
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._build_html())
            elif kind == "pdf":
                doc = QTextDocument()
                doc.setHtml(self._build_html())
                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.A4))
                writer.setResolution(120)
                doc.print_(writer)
            elif kind == "csv":
                self._export_csv(path)
            elif kind == "json":
                payload = {"case": self.ctx.current_case,
                           "generated": datetime.now().isoformat(),
                           "stats": self.ctx.case_manager.stats()}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            else:
                self._export_xml(path)
            self.ctx.notify("Report", f"Exported {kind.upper()} report.")
            self.ctx.log(f"Report exported: {path}", "#00E676")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            self.ctx.log(f"Report export failed: {exc}", "#FF1744")

    def _export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["case_id", "title", "examiner", "created", "artifacts"])
            for row in self.ctx.case_manager.list_cases():
                writer.writerow([row["case_id"], row["title"], row["examiner"],
                                 row["created_at"], row["artifacts"]])

    def _export_xml(self, path: str) -> None:
        root = ET.Element("forensicReport", case=self.ctx.current_case or "\u2014",
                          generated=datetime.now().isoformat())
        for row in self.ctx.case_manager.list_cases():
            case = ET.SubElement(root, "case", case_id=row["case_id"])
            ET.SubElement(case, "title").text = row["title"]
            ET.SubElement(case, "examiner").text = row["examiner"]
            ET.SubElement(case, "artifacts").text = str(row["artifacts"])
        tree = ET.ElementTree(root)
        tree.write(path, encoding="utf-8", xml_declaration=True)
