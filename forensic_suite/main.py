"""Forensic Suite — entry point.

Run with::

    python main.py            # normal mode (empty DB until you extract)
    python main.py --demo     # seeds synthetic demo data for UI testing
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

    # Only seed synthetic demo data when explicitly requested.
    if "--demo" in sys.argv:
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

    # Force opaque painting on Linux compositors. Without these, the
    # window's background defaults to transparent and shows through to
    # whatever is behind it.
    from PySide6.QtCore import Qt
    window.setAttribute(Qt.WA_OpaquePaintEvent, True)
    window.setAttribute(Qt.WA_NoSystemBackground, False)
    window.setAutoFillBackground(True)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
