"""Abstract base class and shared result type for external forensic tools."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ToolResult:
    tool: str
    target: str
    status: str
    output: dict = field(default_factory=dict)
    raw_stdout: str = ""
    raw_stderr: str = ""
    error: str = ""
    command: str = ""
    duration_s: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class ForensicTool(ABC):
    name: str = "unnamed"
    description: str = ""
    homepage: str = ""
    binary_name: str = ""

    # Declarative UI hints read by gui/tabs/tools_tab.py.
    # target_widget: "line" (free text) or "path" (Browse button)
    ui: dict = {
        "target_label": "Target",
        "target_widget": "line",
        "target_placeholder": "",
        "options": [],   # list of {"key","label","widget","placeholder"}
    }

    @classmethod
    def bundled_dir(cls) -> Path:
        return Path(__file__).resolve().parent / "bin" / platform.system().lower()

    @classmethod
    def binary_path(cls) -> Path | None:
        if not cls.binary_name:
            return None
        candidates = [cls.binary_name]
        if platform.system() == "Windows":
            candidates = [f"{cls.binary_name}.exe", cls.binary_name]
        for candidate in candidates:
            bundled = cls.bundled_dir() / candidate
            if bundled.is_file():
                return bundled
            found = shutil.which(candidate)
            if found:
                return Path(found)
        return None

    @classmethod
    def check(cls) -> tuple[bool, str]:
        path = cls.binary_path()
        if path is None:
            return False, (
                f"'{cls.binary_name}' not found. Bundle it in "
                f"tools/bin/{platform.system().lower()}/ or add it to PATH."
            )
        return True, str(path)

    @classmethod
    def run(cls, target: str, timeout: int = 120, **opts) -> ToolResult:
        import time

        path = cls.binary_path()
        if path is None:
            return ToolResult(tool=cls.name, target=target,
                              status="not_installed",
                              error=cls.check()[1])

        args = cls._build_args(target, **opts)
        cmd = [str(path), *args]
        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout, check=False,
                creationflags=_no_window_flag(),
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(tool=cls.name, target=target, status="timeout",
                              command=" ".join(cmd),
                              duration_s=time.monotonic() - started,
                              error=f"Timed out after {timeout}s",
                              raw_stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                              raw_stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "")

        duration = time.monotonic() - started
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            return ToolResult(tool=cls.name, target=target, status="error",
                              command=" ".join(cmd), duration_s=duration,
                              raw_stdout=stdout, raw_stderr=stderr,
                              error=f"Exit code {proc.returncode}")

        try:
            parsed = cls._parse(stdout, stderr, **opts)
        except Exception as exc:
            return ToolResult(tool=cls.name, target=target, status="error",
                              command=" ".join(cmd), duration_s=duration,
                              raw_stdout=stdout, raw_stderr=stderr,
                              error=f"Parse failure: {exc}")

        return ToolResult(tool=cls.name, target=target, status="ok",
                          command=" ".join(cmd), duration_s=duration,
                          output=parsed, raw_stdout=stdout, raw_stderr=stderr)

    @classmethod
    @abstractmethod
    def _build_args(cls, target: str, **opts) -> list[str]:
        ...

    @classmethod
    @abstractmethod
    def _parse(cls, stdout: str, stderr: str, **opts) -> dict:
        ...

    @classmethod
    def _env_overrides(cls) -> dict[str, str]:
        """Extra environment variables passed to the subprocess."""
        return {}


def _no_window_flag() -> int:
    if platform.system() == "Windows":
        return 0x08000000
    return 0