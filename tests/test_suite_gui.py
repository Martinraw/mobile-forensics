"""Offscreen GUI tests for the Forensic Suite (synthetic data only)."""
import os
import sys
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SUITE = Path(__file__).resolve().parent.parent / "forensic_suite"
sys.path.insert(0, str(SUITE))

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from core.ai_client import AIClient
    from core.case_manager import CaseManager
    from core.config import Config
    from core.database import Database
    from gui import AppContext
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    cfg = Config()
    db = Database(tmp_path / "gui.db")
    db.create_all()
    cm = CaseManager(db)
    cm.create_case("G1", "GUI test", "Tester", "TEST-ONLY")
    ctx = AppContext(db=db, config=cfg, case_manager=cm, ai_client=AIClient(cfg))
    win = MainWindow(ctx, cfg)
    win.extraction.shutdown()          # stop the adb polling timer
    yield win, ctx, app
    win.close()


def test_every_tab_opens(window):
    win, _ctx, _app = window
    from gui.main_window import TAB_KEYS
    for key in TAB_KEYS:
        win.show_tab(key)
        assert win.stack.currentWidget() is win.tabs[key]


def test_import_zip_populates_explorer_files_and_overview(window, tmp_path):
    from gui.workers import ImportWorker
    win, ctx, _app = window
    src = tmp_path / "fs.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("sdcard/Download/a.txt", "hello")
        z.writestr("sdcard/Download/b.txt", "hello")      # duplicate content
    case = ctx.case_manager.get_case("G1")
    worker = ImportWorker(ctx, str(tmp_path / "cases"), case, str(src), "file-system archive")
    results = []
    worker.done.connect(lambda i, s: results.append((i, s)))
    worker.failed.connect(lambda m: results.append(("failed", m)))
    worker.run()                                           # synchronous
    assert results and results[0][0] != "failed", results
    ext_id, summary = results[0]
    assert summary["files"] == 2                           # the extracted files; the zip is kept as-is
    rows = ctx.files.query("G1", ext_id)
    assert {r["name"] for r in rows} == {"a.txt", "b.txt"}
    assert all(r["dups"] == 2 for r in rows)               # identical content detected
    win.explorer.refresh()
    case_item = win.explorer.tree.topLevelItem(0)
    assert case_item.childCount() == 1                     # the imported extraction
    win.open_extraction(ext_id)
    assert win.stack.currentWidget() is win.overview
    assert "import" in win.overview.heading.text().lower()
    win.open_section("files", ext_id)
    assert win.stack.currentWidget() is win.files_tab and len(win.files_tab.model.rows) == 2


def test_key_evidence_from_files_tab_updates_explorer(window, tmp_path):
    win, ctx, _app = window
    out = tmp_path / "acq_logical"
    (out / "files").mkdir(parents=True)
    (out / "files" / "x.txt").write_text("evidence")
    ext_id = ctx.case_manager.record_extraction("G1", "dev", "logical", "complete",
                                                out_dir=str(out))
    from core.post_process import process_extraction
    process_extraction(ctx.case_manager, ctx.files, "G1", ext_id, out)
    ctx.current_extraction = ext_id
    win.open_section("files", ext_id)
    ft = win.files_tab
    ft.view.selectRow(0)
    ft._toggle_key_selected()
    assert ctx.files.key_evidence_count("G1", ext_id) == 1
    win.explorer.refresh()
    labels = []

    def walk(item):
        labels.append(item.text(0))
        for i in range(item.childCount()):
            walk(item.child(i))
    walk(win.explorer.tree.topLevelItem(0))
    assert any("Key Evidence" in t and t.rstrip().endswith("1") for t in labels)


def test_data_selection_dialog_marks_root_only_items_disabled(window):
    from gui.dialogs import DataSelectionDialog
    from mobileforensics.acquisition import DATA_ITEMS
    dlg = DataSelectionDialog(None, rooted=False)
    assert len(dlg.selection()) == len(DATA_ITEMS)
    disabled = [dlg.list.item(i) for i in range(dlg.list.count())
                if not (dlg.list.item(i).flags() & Qt.ItemIsEnabled)]
    assert any("Wi-Fi" in d.text() for d in disabled)
