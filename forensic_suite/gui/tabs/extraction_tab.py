"""Extraction tab: device selection, options, live progress and history."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.acquisition_service import (AcquisitionOutcome, AcquisitionRequest,
                                      plan_methods, run_acquisition)
from core.device_manager import detect, hint_for
from widgets.device_card import DeviceCard

class ExtractionWorker(QThread):
    """Runs a REAL acquisition (adb / libimobiledevice) off the UI thread."""

    progress = Signal(str, int)          # message, percent (-1 = unknown)
    finished_outcome = Signal(object)    # AcquisitionOutcome

    def __init__(self, request: AcquisitionRequest, parent=None) -> None:
        super().__init__(parent)
        self.request = request

    def run(self) -> None:
        try:
            outcome = run_acquisition(
                self.request,
                on_progress=lambda msg, pct: self.progress.emit(
                    msg, -1 if pct is None else int(pct)),
                is_cancelled=self.isInterruptionRequested)
        except Exception as exc:  # report, never crash the GUI
            outcome = AcquisitionOutcome(ok=False, message=f"Extraction failed: {exc}")
        self.finished_outcome.emit(outcome)


class DetectWorker(QThread):
    """Runs one device-detection pass off the UI thread (adb can be slow)."""

    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(detect(enrich=True))
        except Exception as exc:  # never let a probe crash the GUI
            from core.device_manager import Detection
            self.done.emit(Detection(level="error",
                                     message=f"Device detection failed: {exc}"))


_LEVEL_COLOR = {"ok": "#00E676", "warn": "#FFAB00",
                "error": "#FF1744", "idle": "#8B949E"}
POLL_MS = 3000


class ExtractionTab(QWidget):
    """Device extraction workspace with live progress + history table."""

    devices_changed = Signal(list)

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.worker: ExtractionWorker | None = None
        self._devices = {}
        self._last_sig = None
        self._detect_worker: DetectWorker | None = None
        self._started_at = 0.0
        self._last_log_key = ""
        self.elapsed_timer: QTimer | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(12)
        heading = QLabel("\U0001F4F1  Extraction")
        heading.setObjectName("SectionTitle")
        head_row = QHBoxLayout()
        head_row.addWidget(heading, 1)
        self.detect_btn = QPushButton("Detect device")
        self.detect_btn.setObjectName("Ghost")
        self.detect_btn.clicked.connect(lambda: self._start_detect(manual=True))
        head_row.addWidget(self.detect_btn)
        left.addLayout(head_row)

        self.detect_label = QLabel("Looking for devices\u2026")
        self.detect_label.setWordWrap(True)
        left.addWidget(self.detect_label)

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
        for cb, why in ((self.chk_cloud, "Cloud acquisition is out of scope for this tool."),
                        (self.chk_sim, "SIM / eSIM acquisition is not implemented.")):
            cb.setEnabled(False)
            cb.setToolTip(why)
            cb.setText(cb.text() + "  (not available)")
        for cb in (self.chk_full, self.chk_logical, self.chk_backup,
                   self.chk_cloud, self.chk_sim):
            opt_lay.addWidget(cb)
        self.chk_encrypt = QCheckBox("Encrypt output (AES-256)  (not available)")
        self.chk_encrypt.setEnabled(False)
        self.chk_encrypt.setToolTip(
            "Not implemented. Store case folders on an encrypted volume "
            "(see docs/ETHICS_AND_AUTHORIZATION.md).")
        opt_lay.addWidget(self.chk_encrypt)

        path_row = QHBoxLayout()
        self.output_path = QLineEdit(str(Path(self.ctx.config.get(
            "extraction", "default_out",
            str(Path.home() / "Downloads" / "forensic_exports"))).expanduser()))
        browse = QPushButton("Browse")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Cases folder"))
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
        self.speed_label = QLabel("Elapsed: \u2014")
        self.eta_label = QLabel("")
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

        self._detect_timer = QTimer(self)
        self._detect_timer.setInterval(POLL_MS)
        self._detect_timer.timeout.connect(self._start_detect)
        self._detect_timer.start()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        self.refresh_devices()

    # ---- device / options / control ----
    def refresh_devices(self) -> None:
        """Start a background detection pass and reload the history table."""
        self._start_detect(manual=True)
        self._refresh_history()

    def shutdown(self) -> None:
        """Stop polling and let any running probe finish (called on app exit)."""
        self._detect_timer.stop()
        worker = self._detect_worker
        if worker is not None and worker.isRunning():
            worker.wait(3000)
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(20000)

    def _set_detect_message(self, text: str, level: str) -> None:
        self.detect_label.setText(text)
        self.detect_label.setStyleSheet(
            f"color:{_LEVEL_COLOR.get(level, '#8B949E')};")

    def _start_detect(self, manual: bool = False) -> None:
        if self._detect_worker is not None and self._detect_worker.isRunning():
            return
        if self.worker is not None and self.worker.isRunning():
            return  # leave the device alone while an extraction is running
        if manual:
            self.detect_btn.setEnabled(False)
            self._set_detect_message("Detecting\u2026", "idle")
        self._detect_worker = DetectWorker()
        self._detect_worker.done.connect(self._on_detected)
        self._detect_worker.start()

    def _on_detected(self, result) -> None:
        self.detect_btn.setEnabled(True)
        self._set_detect_message(result.message, result.level)
        signature = tuple((d.serial, d.state, d.model) for d in result.devices)
        if signature == self._last_sig:
            return  # nothing changed; keep the user's selection untouched
        previous = {item[0] for item in (self._last_sig or ())}
        self._last_sig = signature

        keep = self.device_combo.currentData()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self._devices = {}
        for device in result.devices:
            self._devices[device.serial] = device
            rooted = "  (rooted)" if device.rooted else ""
            state = "" if device.state == "device" else f"  [{device.state}]"
            self.device_combo.addItem(
                f"{device.platform} \u2014 {device.model}{rooted}{state}",
                device.serial)
        index = self.device_combo.findData(keep)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(False)
        self._device_changed()

        current = {d.serial for d in result.devices}
        for device in result.devices:
            if device.serial not in previous:
                self.ctx.log(f"Device detected: {device.display_name} "
                             f"[{device.state}]", "#00E5FF")
        for serial in previous - current:
            self.ctx.log(f"Device disconnected: {serial}", "#FFAB00")
        self.devices_changed.emit(list(result.devices))

    def _device_changed(self) -> None:
        serial = self.device_combo.currentData()
        device = self._devices.get(serial)
        self.device_card.set_device(device)
        if device is None:
            return
        if device.state == "device":
            self.ctx.status(f"Device: {device.model}", "ok", 100)
        else:
            self.ctx.status(f"Device {device.state}", "error", 0)
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

    def _active_case(self):
        case = self.ctx.case_manager.get_case(self.ctx.current_case)
        if case is None:
            self.ctx.notify("Extraction",
                            "No active case. Create a case first; it records the "
                            "examiner and the authorization reference.")
            self.ctx.show_new_case_dialog()
        return case

    def _start(self) -> None:
        device = self.device_card.device
        if device is None:
            self.ctx.notify("Extraction", "Select a device first.")
            return
        if device.state != "device":
            self.ctx.notify("Extraction",
                            f"Device is '{device.state}'. {hint_for(device)}")
            return
        methods, problem = plan_methods(device, self.chk_full.isChecked(),
                                        self.chk_logical.isChecked(),
                                        self.chk_backup.isChecked())
        if problem:
            self.ctx.notify("Extraction", problem)
            return
        case = self._active_case()
        if case is None:
            return
        answer = QMessageBox.question(
            self, "Confirm authorization",
            f"Extract data from {device.model} ({device.serial})?\n\n"
            f"Case: {case.case_id}\nAuthorization: {case.authorization_ref}\n"
            f"Examiner: {case.examiner}\nMethods: {', '.join(methods)}\n\n"
            "Continue only if you own this device or hold written authorization "
            "to examine it. This confirmation is recorded in the audit log.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return

        request = AcquisitionRequest(
            cases_root=Path(self.output_path.text()).expanduser(),
            case_id=case.case_id, examiner=case.examiner,
            authorization=case.authorization_ref, device=device, methods=methods,
            verify=bool(self.ctx.config.get("extraction", "verify_hashes", True)))

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.stage_label.setText("Starting\u2026")
        self.eta_label.setText(f"Case: {case.case_id}")
        self._last_log_key = ""
        self.ctx.add_custody(case.examiner,
                             f"extraction_started device={device.serial} "
                             f"methods={','.join(methods)}")
        self.ctx.status("Extracting\u2026", "busy", 0)
        self._on_log(f"Starting extraction on {device.model}: {', '.join(methods)}",
                     "#00E5FF")
        self._extract_case = case
        self.worker = ExtractionWorker(request, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_outcome.connect(self._on_finished)
        self.worker.start()

        self._started_at = time.monotonic()
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._tick_elapsed)
        self.elapsed_timer.start()

    def _tick_elapsed(self) -> None:
        secs = int(time.monotonic() - self._started_at)
        self.speed_label.setText(
            f"Elapsed: {secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}")

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.requestInterruption()
            self._on_log("Cancelling\u2026 collected data will be kept and hashed.",
                         "#FFAB00")
        self.cancel_btn.setEnabled(False)

    # ---- progress wiring ----
    def _on_progress(self, message: str, percent: int) -> None:
        self.stage_label.setText(message[:110])
        if percent >= 0:
            self.progress.setValue(min(percent, 100))
            self.ctx.status(message[:40], "busy", min(percent, 100))
        words = message.split()
        key = words[0] if words else ""
        if len(words) > 1 and words[1].startswith("/"):
            key += " " + words[1]
        if key != self._last_log_key:      # log each new step once, not every line
            self._last_log_key = key
            self._on_log(message[:140], "#8B949E")

    def _on_log(self, message: str, color: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendHtml(
            f'<span style="color:{color};">[{stamp}] {message}</span>')
        self.ctx.log(message, color)

    def _on_finished(self, outcome: AcquisitionOutcome) -> None:
        if self.elapsed_timer is not None:
            self.elapsed_timer.stop()
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setValue(100 if outcome.ok else self.progress.value())
        self.stage_label.setText("Idle" if outcome.ok else "Stopped")
        color = "#00E676" if outcome.ok else ("#FFAB00" if outcome.cancelled else "#FF1744")
        self.ctx.status("Idle", "ok" if outcome.ok else "error",
                        100 if outcome.ok else 0)
        self._on_log(outcome.message, color)

        case = getattr(self, "_extract_case", None)
        device = self.device_card.device
        for res in outcome.results:
            size = res.size_bytes / (1024 ** 2)
            self._on_log(f"{res.method}: {res.status}, {res.files} files, "
                         f"{size:.1f} MB -> {res.out_dir}"
                         + (f"  (verified: {res.verified})" if res.verified is not None else ""),
                         color)
            for err in res.errors[:5]:
                self._on_log(f"  warning: {err[:160]}", "#FFAB00")
            if res.manifest_sha256:
                self._on_log(f"  manifest sha256 {res.manifest_sha256}", "#8B949E")
            if case is not None:
                try:
                    self.ctx.case_manager.record_extraction(
                        case.case_id, device.model if device else "device",
                        res.method, res.status, files=res.files,
                        size_bytes=res.size_bytes)
                except Exception as exc:
                    self._on_log(f"Could not record extraction: {exc}", "#FF1744")
        if case is not None:
            self.ctx.add_custody(
                case.examiner,
                "extraction_complete" if outcome.ok else
                ("extraction_cancelled" if outcome.cancelled else "extraction_failed"))
        self.ctx.notify("Extraction", outcome.message)
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
