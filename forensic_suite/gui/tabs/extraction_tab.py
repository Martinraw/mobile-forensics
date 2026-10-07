"""Extraction tab: device selection, options, live progress and history."""
from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.device_manager import connected_devices
from widgets.device_card import DeviceCard

STAGES = [
    ("Connecting device", 15),
    ("Acquiring data", 45),
    ("Parsing artifacts", 75),
    ("Hashing evidence", 95),
]


class ExtractionWorker(QThread):
    """Simulated staged extraction running off the UI thread."""

    stage_changed = Signal(str, int)
    log_line = Signal(str, str)
    finished_ok = Signal(str, bool)

    def __init__(self, device_name: str, options: str, out_dir: str,
                 parent=None) -> None:
        super().__init__(parent)
        self.device_name = device_name
        self.options = options
        self.out_dir = out_dir

    def run(self) -> None:
        try:
            for index, (name, base) in enumerate(STAGES):
                next_base = STAGES[index + 1][1] if index + 1 < len(STAGES) else 100
                self.log_line.emit(f"Starting: {name}", "#00E5FF")
                self.stage_changed.emit(name, base)
                for step in range(base, next_base):
                    if self.isInterruptionRequested():
                        self.finished_ok.emit("Extraction cancelled by user.", False)
                        return
                    self.stage_changed.emit(name, step)
                    self.msleep(30 + (step % 7) * 5)
            self.log_line.emit(
                f"Complete -> {self.out_dir}  [{self.options}]", "#00E676")
            self.finished_ok.emit(
                "Extraction complete. Evidence hashed and logged.", True)
        except Exception as exc:
            self.finished_ok.emit(f"Extraction failed: {exc}", False)


class ExtractionTab(QWidget):
    """Device extraction workspace with live progress + history table."""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.worker: ExtractionWorker | None = None
        self.speed_timer: QTimer | None = None
        self._devices = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(12)
        heading = QLabel("\U0001F4F1  Extraction")
        heading.setObjectName("SectionTitle")
        left.addWidget(heading)

        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        left.addWidget(self.device_combo)

        self.device_card = DeviceCard()
        left.addWidget(self.device_card)

        options = QWidget()
        options.setObjectName("Card")
        opt_lay = QVBoxLayout(options)
        opt_lay.setContentsMargins(12, 12, 12, 12)
        opt_lay.setSpacing(6)
        opt_lay.addWidget(QLabel("Extraction options"))
        self.chk_full = QCheckBox("Full file-system (rooted device)")
        self.chk_logical = QCheckBox("Logical (SMS, calls, contacts)")
        self.chk_backup = QCheckBox("Backup")
        self.chk_cloud = QCheckBox("Cloud accounts")
        self.chk_sim = QCheckBox("SIM / eSIM")
        self.chk_logical.setChecked(True)
        for cb in (self.chk_full, self.chk_logical, self.chk_backup,
                   self.chk_cloud, self.chk_sim):
            opt_lay.addWidget(cb)
        self.chk_encrypt = QCheckBox("Encrypt output (AES-256)")
        opt_lay.addWidget(self.chk_encrypt)

        path_row = QHBoxLayout()
        self.output_path = QLineEdit(
            str(Path.home() / "Downloads" / "forensic_exports"))
        browse = QPushButton("Browse")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Output"))
        path_row.addWidget(self.output_path, 1)
        path_row.addWidget(browse)
        opt_lay.addLayout(path_row)

        self.start_btn = QPushButton("\u25B6  START EXTRACTION")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumHeight(44)
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.start_btn, 2)
        btn_row.addWidget(self.cancel_btn, 1)
        opt_lay.addLayout(btn_row)

        left.addWidget(options)
        left.addStretch()
        layout.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(12)

        progress_card = QWidget()
        progress_card.setObjectName("Card")
        prog_lay = QVBoxLayout(progress_card)
        prog_lay.setContentsMargins(12, 12, 12, 12)
        prog_lay.addWidget(QLabel("Live progress"))
        self.stage_label = QLabel("Idle")
        self.stage_label.setObjectName("CardTitle")
        prog_lay.addWidget(self.stage_label)
        self.progress = QProgressBar()
        prog_lay.addWidget(self.progress)
        meta = QHBoxLayout()
        self.speed_label = QLabel("Speed: \u2014")
        self.eta_label = QLabel("ETA: \u2014")
        meta.addWidget(self.speed_label)
        meta.addStretch()
        meta.addWidget(self.eta_label)
        prog_lay.addLayout(meta)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(140)
        self.log_view.setStyleSheet(
            "font-family:'JetBrains Mono','Consolas',monospace; font-size:11px; "
            "background:#0D1117; border:1px solid #30363D; border-radius:6px;")
        prog_lay.addWidget(self.log_view)
        right.addWidget(progress_card, 1)

        history_card = QWidget()
        history_card.setObjectName("Card")
        hist_lay = QVBoxLayout(history_card)
        hist_lay.setContentsMargins(12, 12, 12, 12)
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(
            ["Time", "Device", "Method", "Status", "Files", "Size"])
        self.history.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history.verticalHeader().setVisible(False)
        hist_lay.addWidget(QLabel("Extraction history"))
        hist_lay.addWidget(self.history)
        right.addWidget(history_card, 1)

        layout.addLayout(right, 3)
        self.refresh_devices()

    # ---- device / options / control ----
    def refresh_devices(self) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self._devices = {}
        for device in connected_devices():
            self._devices[device.serial] = device
            rooted = "  (rooted)" if device.rooted else ""
            self.device_combo.addItem(
                f"{device.platform} \u2014 {device.model}{rooted}", device.serial)
        self.device_combo.blockSignals(False)
        self._device_changed()
        self._refresh_history()

    def _device_changed(self) -> None:
        serial = self.device_combo.currentData()
        device = self._devices.get(serial)
        self.device_card.set_device(device)
        if device is not None:
            self.ctx.status(f"Device: {device.model}", "ok", 100)
            self.ctx.log(f"Selected device {device.model} ({device.serial})", "#00E5FF")

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Output folder", self.output_path.text())
        if path:
            self.output_path.setText(path)

    def _selected_options(self) -> str:
        chosen = [name for cb, name in (
            (self.chk_full, "Full FS"), (self.chk_logical, "Logical"),
            (self.chk_backup, "Backup"), (self.chk_cloud, "Cloud"),
            (self.chk_sim, "SIM")) if cb.isChecked()]
        return ", ".join(chosen) or "Logical"

    def _start(self) -> None:
        device = self.device_card.device
        if device is None:
            self.ctx.notify("Extraction", "Select a device first.")
            return
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.eta_label.setText("ETA: ~12s")
        self.ctx.add_custody("analyst", f"extraction_started device={device.serial}")
        self.ctx.status("Extracting\u2026", "busy", 0)
        self.ctx.log(f"Starting extraction on {device.model}", "#00E5FF")
        self.worker = ExtractionWorker(
            device.model, self._selected_options(), self.output_path.text(), self)
        self.worker.stage_changed.connect(self._on_stage)
        self.worker.log_line.connect(self._on_log)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.start()

        self.speed_timer = QTimer(self)
        self.speed_timer.setInterval(800)
        self.speed_timer.timeout.connect(self._tick_speed)
        self.speed_timer.start()

    def _tick_speed(self) -> None:
        mode = "encrypted" if self.chk_encrypt.isChecked() else "plain"
        self.speed_label.setText(
            f"Speed: {random.randint(18, 42)} MB/s  ({mode})")

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.requestInterruption()
        self.cancel_btn.setEnabled(False)

    # ---- progress wiring ----
    def _on_stage(self, name: str, percent: int) -> None:
        self.stage_label.setText(name)
        self.progress.setValue(percent)
        self.ctx.status(name, "busy", percent)

    def _on_log(self, message: str, color: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendHtml(
            f'<span style="color:{color};">[{stamp}] {message}</span>')
        self.ctx.log(message, color)

    def _on_finished(self, message: str, ok: bool) -> None:
        if self.speed_timer is not None:
            self.speed_timer.stop()
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.eta_label.setText("ETA: done")
        self.progress.setValue(100 if ok else 0)
        self.ctx.status("Idle", "ok" if ok else "error", 100 if ok else 0)
        self.ctx.log(message, "#00E676" if ok else "#FF1744")
        self.ctx.add_custody("analyst",
                             "extraction_complete" if ok else "extraction_failed")
        self.ctx.notify("Extraction", message)
        if ok and self.device_card.device is not None:
            try:
                self.ctx.case_manager.record_extraction(
                    self.ctx.current_case or "DEMO001",
                    self.device_card.device.model,
                    self._selected_options(), "complete",
                    files=random.randint(800, 15_000),
                    size_bytes=random.randint(500_000_000, 4_000_000_000))
            except Exception as exc:
                self.ctx.log(f"Could not record extraction: {exc}", "#FF1744")
        self._refresh_history()

    def _refresh_history(self) -> None:
        rows = self.ctx.case_manager.list_extractions()
        self.history.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            values = [entry["started"], entry["device"], entry["method"],
                      entry["status"], str(entry["files"]),
                      f"{entry['size_bytes'] / (1024 ** 3):.2f} GB"]
            for col, value in enumerate(values):
                self.history.setItem(row, col, QTableWidgetItem(value))
        self.history.resizeColumnsToContents()
