"""Wrapper around PhoneInfoga (https://github.com/sundowndev/phoneinfoga).

v2.11.0 CLI reality check (from `phoneinfoga --help`):
  * Root-level flags: only -h / --help
  * No --no-color, no --no-ansi
  * Correct invocation: `phoneinfoga scan -n <number>`
  * Extra scanners: `--plugin <name>` (repeatable, on the scan subcommand)
  * Color output is minimal; we strip ANSI escapes defensively in _parse().
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import ForensicTool


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class PhoneInfoga(ForensicTool):
    name = "phoneinfoga"
    description = "Phone number OSINT reconnaissance (carrier, country, footprint)."
    homepage = "https://github.com/sundowndev/phoneinfoga"
    binary_name = "phoneinfoga"

    ui = {
        "target_label": "Phone number",
        "target_widget": "line",
        "target_placeholder": "e.g. +260971234567",
        "options": [],
    }

    @classmethod
    def _build_args(cls, target: str, **opts) -> list[str]:
        # v2.11.0: only `scan -n <number>` is valid. No global color flags.
        args: list[str] = ["scan", "-n", target]
        scanners = opts.get("scanners")
        if scanners:
            for s in scanners:
                args += ["--plugin", s]
        return args

    @classmethod
    def _env_overrides(cls) -> dict[str, str]:
        # Harmless: some tools respect NO_COLOR even if this build doesn't.
        return {"NO_COLOR": "1"}

    @classmethod
    def _parse(cls, stdout: str, stderr: str, **opts) -> dict:
        clean = _ANSI.sub("", stdout).strip()
        parsed = {"number": opts.get("target", ""), "raw_text": clean}
        json_blob = _extract_json(clean)
        if json_blob is not None:
            parsed["json"] = json_blob
            for key in ("valid", "country", "carrier", "line_type", "local"):
                if key in json_blob:
                    parsed[key] = json_blob[key]
        else:
            parsed.update(_scrape_key_values(clean))
        return parsed


def _extract_json(text: str) -> dict | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


_KV_PATTERN = re.compile(r"^\s*([A-Za-z][A-Za-z _-]+):\s*(.+?)\s*$")


def _scrape_key_values(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        match = _KV_PATTERN.match(line)
        if match:
            key = match.group(1).strip().lower().replace(" ", "_")
            out[key] = match.group(2).strip()
    return out


def ensure_binary_placeholder() -> Path:
    return PhoneInfoga.bundled_dir()