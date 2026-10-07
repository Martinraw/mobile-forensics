"""Tools tab: enumerate, check, and run bundled external forensic tools.

The form is rebuilt each time the user selects a tool, driven by each
ForensicTool subclass's ``ui`` dict. No command typing required — the widget
type is chosen automatically ("line" for free text, "path" for a Browse
button).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from tools import available_tools, get_tool
from tools.base import ForensicTool, ToolResult


class _Worker(QThread):
    """Runs ``ForensicTool.run`` off the GUI thread."""

    finished_result = Signal(object)

    def __init__(self, tool_cls: type[ForensicTool], target: str,
                 opts: dict, parent=None) -> None:
        super().__init__(parent)
        self.tool_cls = tool_cls
        self.target = target
        self.opts = opts

    def run(self) -> None:
        result = self.tool_cls.run(self.target, **self.opts)
        self.finished_result.emit(result)


class ToolsTab(QWidget):
    """Left = tool list, right = form + results. Fully button-driven."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._worker: _Worker | None = None
        self._target_widget: QWidget | None = None
        self._option_widgets: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QLabel("External Tools")
        header.setObjectName("CardTitle")
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        # ---- left: tool list ----
        self.list = QListWidget()
        self.list.setObjectName("ToolList")
        self.list.setMinimumWidth(220)
        for tool_cls in available_tools():
            installed, _where = tool_cls.check()
            dot = "\u25CF" if installed else "\u25CB"
            item = QListWidgetItem(f"{dot}  {tool_cls.name}")
            item.setToolTip(tool_cls.description)
            item.setData(Qt.UserRole, tool_cls.name)
            self.list.addItem(item)
        self.list.currentItemChanged.connect(self._on_tool_selected)
        splitter.addWidget(self.list)

        # ---- right: info + dynamic form + results ----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.info = QLabel("Select a tool on the left.")
        self.info.setWordWrap(True)
        self.info.setProperty("role", "muted")
        right_layout.addWidget(self.info)

        self.form_box = QGroupBox("Run")
        self.form = QFormLayout(self.form_box)
        self.form.setLabelAlignment(Qt.AlignRight)
        right_layout.addWidget(self.form_box)

        # action row
        buttons = QHBoxLayout()
        self.check_btn = QPushButton("Re-check availability")
        self.check_btn.clicked.connect(self._recheck)
        self.run_btn = QPushButton("Run")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._run)
        buttons.addWidget(self.check_btn)
        buttons.addStretch()
        buttons.addWidget(self.run_btn)
        right_layout.addLayout(buttons)

        results_label = QLabel("Results")
        results_label.setObjectName("CardTitle")
        right_layout.addWidget(results_label)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Key", "Value"])
        self.tree.setColumnWidth(0, 220)
        right_layout.addWidget(self.tree, 2)

        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setPlaceholderText("Raw tool output will appear here.")
        right_layout.addWidget(self.raw, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 780])
        root.addWidget(splitter, 1)

        if self.list.count():
            self.list.setCurrentRow(0)

    # ---------- dynamic form construction ----------
    def _rebuild_form(self, tool_cls: type[ForensicTool]) -> None:
        """Clear and rebuild the form based on tool_cls.ui."""
        # Wipe existing rows
        while self.form.rowCount():
            self.form.removeRow(0)
        self._target_widget = None
        self._option_widgets.clear()

        ui = getattr(tool_cls, "ui", {}) or {}
        target_label = ui.get("target_label", "Target")
        widget_kind = ui.get("target_widget", "line")
        placeholder = ui.get("target_placeholder", "")

        if widget_kind == "path":
            # Row: [QLineEdit (readonly)] [Browse...]
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            line = QLineEdit()
            line.setPlaceholderText(placeholder)
            line.setReadOnly(True)
            browse = QPushButton("Browse\u2026")
            browse.setFixedWidth(90)
            browse.clicked.connect(self._browse_target)
            row_layout.addWidget(line, 1)
            row_layout.addWidget(browse)
            self.form.addRow(target_label, row)
            self._target_widget = line
        else:
            line = QLineEdit()
            line.setPlaceholderText(placeholder)
            self.form.addRow(target_label, line)
            self._target_widget = line

        # Declarative extra options (empty for now, ready for the next tool)
        for opt in ui.get("options", []):
            key = opt["key"]
            label = opt.get("label", key)
            kind = opt.get("widget", "line")
            placeholder = opt.get("placeholder", "")
            if kind == "line":
                w = QLineEdit()
                w.setPlaceholderText(placeholder)
            else:
                w = QLineEdit()
            self.form.addRow(label, w)
            self._option_widgets[key] = w

    def _browse_target(self) -> None:
        """Open a picker. Offers both file and folder since ALEAPP takes either."""
        dialog = QFileDialog(self, "Choose extraction (zip/tar/gz or folder)")
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setOption(QFileDialog.ShowDirsOnly, False)
        # We need both modes; QFileDialog can't do that in one call, so ask.
        choice = QMessageBox.question(
            self, "Choose input type",
            "Pick a <b>compressed file</b> (.zip/.tar/.gz) or a <b>folder</b>?",
            QMessageBox.Open | QMessageBox.Cancel)
        if choice == QMessageBox.Open:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose extraction file",
                filter="Extractions (*.zip *.tar *.gz *.tgz);;All files (*)")
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Choose extraction folder")
        if path and self._target_widget is not None:
            self._target_widget.setText(path)

    # ---------- handlers ----------
    def _current_tool(self) -> type[ForensicTool] | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return get_tool(item.data(Qt.UserRole))

    def _on_tool_selected(self) -> None:
        tool_cls = self._current_tool()
        if tool_cls is None:
            return
        installed, where = tool_cls.check()
        state = "installed" if installed else "not installed"
        self.info.setText(
            f"<b>{tool_cls.name}</b> \u2014 {tool_cls.description}<br/>"
            f"<span style='color:#8B949E'>Status: {state}<br/>"
            f"Location: {where}<br/>"
            f"Homepage: <a href='{tool_cls.homepage}'>{tool_cls.homepage}</a></span>"
        )
        self.info.setOpenExternalLinks(True)
        self._rebuild_form(tool_cls)
        self.run_btn.setEnabled(installed)

    def _recheck(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            tool_cls = get_tool(item.data(Qt.UserRole))
            if tool_cls is None:
                continue
            installed, _ = tool_cls.check()
            dot = "\u25CF" if installed else "\u25CB"
            item.setText(f"{dot}  {tool_cls.name}")
        self._on_tool_selected()

    def _run(self) -> None:
        tool_cls = self._current_tool()
        if tool_cls is None or self._target_widget is None:
            return
        target = self._target_widget.text().strip() if hasattr(self._target_widget, "text") \
                 else ""
        if not target:
            QMessageBox.warning(self, "Run tool",
                                "Pick a target first (type or Browse).")
            return

        opts: dict = {}
        for key, widget in self._option_widgets.items():
            if hasattr(widget, "text") and widget.text().strip():
                opts[key] = widget.text().strip()

        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running\u2026")
        self.tree.clear()
        self.raw.setPlainText("Running\u2026")

        self._worker = _Worker(tool_cls, target, opts, parent=self)
        self._worker.finished_result.connect(self._on_result)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_result(self, result: ToolResult) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run")

        self.raw.setPlainText(
            f"$ {result.command}\n"
            f"[status={result.status}  duration={result.duration_s:.2f}s]\n\n"
            f"--- stdout ---\n{result.raw_stdout}\n\n"
            f"--- stderr ---\n{result.raw_stderr}\n\n"
            f"--- error ---\n{result.error}"
        )

        self.tree.clear()
        if result.output:
            for key, value in result.output.items():
                node = QTreeWidgetItem([str(key), _short(value)])
                if isinstance(value, dict):
                    for k2, v2 in value.items():
                        node.addChild(QTreeWidgetItem([str(k2), _short(v2)]))
                self.tree.addTopLevelItem(node)
            self.tree.expandToDepth(1)

        case_id = getattr(self.ctx, "current_case", None)
        if case_id and result.status == "ok":
            try:
                self.ctx.case_manager.add_tool_run(
                    case_id=case_id, tool=result.tool, target=result.target,
                    status=result.status, command=result.command,
                    duration_s=result.duration_s, output=result.output,
                )
                self.ctx.log(f"{result.tool} run recorded for {case_id}",
                             "#00E5FF")
            except Exception as exc:
                self.ctx.log(f"Failed to save tool run: {exc}", "#FF6B6B")


def _short(value) -> str:
    text = str(value)
    return text if len(text) <= 120 else text[:117] + "\u2026"