"""Background workers so indexing / importing never freezes the UI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.post_process import process_extraction


class IndexWorker(QThread):
    """Parse + index one extraction folder."""

    progress = Signal(str, int)
    done = Signal(int, dict)       # extraction_id, summary
    failed = Signal(int, str)

    def __init__(self, ctx, case_id: str, extraction_id: int, root: str, parent=None) -> None:
        super().__init__(parent)
        self.ctx, self.case_id, self.extraction_id, self.root = ctx, case_id, extraction_id, root

    def run(self) -> None:
        try:
            summary = process_extraction(
                self.ctx.case_manager, self.ctx.files, self.case_id, self.extraction_id,
                Path(self.root), progress=lambda m, p: self.progress.emit(m, p),
                cancelled=self.isInterruptionRequested)
            self.done.emit(self.extraction_id, summary)
        except Exception as exc:
            self.failed.emit(self.extraction_id, str(exc))


class ImportWorker(QThread):
    """Copy + hash + (extract) + index evidence made by another tool."""

    progress = Signal(str, int)
    done = Signal(int, dict)
    failed = Signal(str)

    def __init__(self, ctx, cases_root: str, case, source: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.ctx, self.cases_root, self.case = ctx, cases_root, case
        self.source, self.label = source, label

    def run(self) -> None:
        from core.acquisition_service import import_to_case
        try:
            res = import_to_case(Path(self.cases_root), self.case.case_id, self.case.examiner,
                                 self.case.authorization_ref, Path(self.source),
                                 on_progress=lambda m, p: self.progress.emit(m, p))
            ext_id = self.ctx.case_manager.record_extraction(
                self.case.case_id, Path(self.source).name, f"import: {self.label}", "complete",
                files=res.files, size_bytes=res.size_bytes, out_dir=res.index_root,
                info={"platform": "Imported", "source": self.source,
                      "source_sha256": res.sha256, "imported_copy": res.imported})
            summary = process_extraction(
                self.ctx.case_manager, self.ctx.files, self.case.case_id, ext_id,
                Path(res.index_root), progress=lambda m, p: self.progress.emit(m, p),
                cancelled=self.isInterruptionRequested)
            self.done.emit(ext_id, summary)
        except Exception as exc:
            self.failed.emit(str(exc))
