"""Headless smoke test: fully build the GUI offscreen and auto-quit.

Run with:  python scripts/smoke_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.ai_client import AIClient
from core.case_manager import CaseManager
from core.config import Config
from core.database import Database
from gui import AppContext, load_stylesheet
from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    config = Config()
    db = Database()
    db.create_all()
    case_manager = CaseManager(db)
    case_manager.seed_demo()
    ctx = AppContext(db=db, config=config, case_manager=case_manager,
                     ai_client=AIClient(config))
    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)
    app.setFont(QFont("Segoe UI", 13))

    window = MainWindow(ctx, config)
    window.show()

    def report() -> None:
        stats = case_manager.stats()
        print(f"cases={stats['cases']} devices={stats['devices']} "
              f"data_gb={stats['data_gb']} categories={len(stats['categories'])}")
        print("active tab:", window.stack.currentIndex())
        print("SMOKE OK")
        app.quit()

    QTimer.singleShot(3500, report)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())