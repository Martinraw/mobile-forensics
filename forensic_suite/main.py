"""Forensic Suite \u2014 entry point.

Run with::

    python main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    app.setApplicationName("Forensic Suite")
    app.setOrganizationName("ForensicSuite")
    app.setApplicationVersion("0.1.0")
    app.setStyle("Fusion")

    config = Config()
    database = Database()
    database.create_all()
    case_manager = CaseManager(database)
    case_manager.seed_demo()
    ai_client = AIClient(config)
    ctx = AppContext(db=database, config=config, case_manager=case_manager,
                     ai_client=ai_client)

    if config.get("appearance", "theme", "dark") == "dark":
        stylesheet = load_stylesheet()
        if stylesheet:
            app.setStyleSheet(stylesheet)

    font_size = int(config.get("appearance", "font_size", 13))
    app.setFont(QFont("Segoe UI", font_size))

    window = MainWindow(ctx, config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())