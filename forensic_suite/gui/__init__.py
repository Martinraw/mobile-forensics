"""GUI package — PySide6 application shell."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.ai_client import AIClient
from core.case_manager import CaseManager
from core.config import Config
from core.database import Database
from core.evidence_files import EvidenceFiles

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
    current_extraction: int | None = None
    files: EvidenceFiles | None = None
    # Navigation hooks, wired by MainWindow.
    open_extraction: Callable[[int], None] = lambda _id: None
    open_section: Callable[[str, int | None], None] = lambda _s, _i: None
    refresh_explorer: Callable[[], None] = lambda: None
    import_evidence: Callable[[str], None] = lambda _kind: None
    process_extraction: Callable[[str, int, str], None] = lambda _c, _e, _d: None

    def __post_init__(self) -> None:
        if self.files is None:
            self.files = EvidenceFiles(self.db)