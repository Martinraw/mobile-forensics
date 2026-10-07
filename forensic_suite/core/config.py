"""Application configuration persisted as JSON in the user home directory."""
from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULTS: dict = {
    "appearance": {
        "theme": "dark",
        "font_size": 13,
        "language": "English",
    },
    "extraction": {
        "default_out": "~/Downloads/forensic_exports",
        "verify_hashes": True,
    },
    "ai": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.4,
    },
    "privacy": {
        "telemetry": False,
        "autosave": True,
    },
}


class Config:
    """Thin JSON-backed settings store (single source of truth for the GUI)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.home() / ".forensic_suite" / "config.json")
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = copy.deepcopy(DEFAULTS)

    def get(self, section: str, key: str, default=None):
        return self.data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: object) -> None:
        self.data.setdefault(section, {})[key] = value
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def reset(self) -> None:
        self.data = copy.deepcopy(DEFAULTS)
        self.save()