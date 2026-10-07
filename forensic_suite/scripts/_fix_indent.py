"""Fix chunk-split indentation regressions in the generated modules."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FIXES: dict[str, dict[str, int]] = {
    "gui/main_window.py": {
        "def _build_central(self) -> None:": 4,
        "def show_tab(self, key: str) -> None:": 4,
    },
    "gui/tabs/extraction_tab.py": {
        "right = QVBoxLayout()": 8,
        "def _start(self) -> None:": 4,
    },
    "gui/tabs/reports_tab.py": {
        "def _generate(self) -> None:": 4,
        "def _export(self, kind: str) -> None:": 4,
        "def _export_csv(self, path: str) -> None:": 4,
        "def _export_xml(self, path: str) -> None:": 4,
    },
    "gui/tabs/settings_tab.py": {
        "def _load(self) -> None:": 4,
    },
    "gui/tabs/timeline_tab.py": {
        "def _apply(self) -> None:": 4,
    },
}


def main() -> None:
    for rel, replacements in FIXES.items():
        path = ROOT / rel
        lines = path.read_text(encoding="utf-8").splitlines()
        changed = 0
        for needle, pad in replacements.items():
            for i, line in enumerate(lines):
                if line == needle:
                    lines[i] = " " * pad + line
                    changed += 1
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{rel}: {changed} line(s) re-indented")


if __name__ == "__main__":
    main()