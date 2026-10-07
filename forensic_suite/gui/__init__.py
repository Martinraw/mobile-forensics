"""GUI package — PySide6 application shell."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.ai_client import AIClient
from core.case_manager import CaseManager
from core.config import Config
from core.database import Database

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
STYLE_PATH = ASSETS_DIR / "styles" / "dark_theme.qss"


def load_stylesheet() -> str:
    """Read the compiled QSS theme (falls back to an empty string)."""
    try:
        return STYLE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


@dataclass
class AppContext:
    """Shared services injected into every tab/widget."""

    db: Database
    config: Config
    case_manager: CaseManager
    ai_client: AIClient
    navigate: Callable[[str], None] = lambda _key: None
    notify: Callable[[str, str], None] = lambda _title, _msg: None
    status: Callable[[str, str, int], None] = lambda _task, _state, _prog: None
    log: Callable[[str, str], None] = lambda _msg, _color: None
    add_custody: Callable[[str, str], None] = lambda _user, _action: None
    show_new_case_dialog: Callable[[], None] = lambda: None
    current_case: str = "—"