"""Wrapper around ALEAPP (https://github.com/abrignoni/ALEAPP).

ALEAPP ships as a PyInstaller bundle for Windows (aleapp.exe + _internal/).
On Linux it ships as an AppImage, macOS as a .dmg. This wrapper locates the
Windows launcher inside tools/bin/windows/aleapp/ and invokes it as a
subprocess.

CLI (per ALEAPP docs):
    aleapp -t <zip | tar | fs | gz> -i <input_path> -o <output_dir>
"""
from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path

from .base import ForensicTool, ToolResult, _no_window_flag


class ALEAPP(ForensicTool):
    name = "aleapp"
    description = "Android artifact parser (SMS, calls, locations, apps, ...)."
    homepage = "https://github.com/abrignoni/ALEAPP"
    binary_name = "aleapp"

    ui = {
        "target_label": "Extraction (zip or folder)",
        "target_widget": "path",
        "target_placeholder": "Choose a .zip file or an extracted folder",
        "options": [],
    }

    # ---------- binary discovery ----------
    @classmethod
    def binary_path(cls) -> Path | None:
        """Find the launcher inside the bundled PyInstaller folder."""
        bundled = cls.bundled_dir()  # tools/bin/<os>/

        if platform.system() == "Windows":
            # Prefer: tools/bin/windows/aleapp/aleapp.exe
            for candidate in (
                bundled / "aleapp" / "aleapp.exe",
                bundled / "aleapp.exe",
            ):
                if candidate.is_file():
                    return candidate

        # Linux/macOS fallback ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â a source clone or AppImage
        for candidate in (
            bundled / "aleapp" / "aleapp.py",
            bundled / "aleapp",
        ):
            if candidate.is_file():
                return candidate

        # Last resort: system PATH
        return super().binary_path()

    @classmethod
    def check(cls) -> tuple[bool, str]:
        path = cls.binary_path()
        if path is None:
            return False, (
                f"ALEAPP not found. Expected at "
                f"tools/bin/{platform.system().lower()}/aleapp/"
            )
        return True, str(path)

    # ---------- execution ----------
    @classmethod
    def _build_args(cls, target: str, **opts) -> list[str]:
        target_path = Path(target)
        suffix = target_path.suffix.lower()
        if suffix in (".zip", ".tar", ".gz", ".tgz"):
            input_type = {"zip": "zip", "tar": "tar", "gz": "tar", "tgz": "tar"}[suffix.lstrip(".")]
        elif target_path.is_dir():
            input_type = "fs"
        else:
            suffix = target_path.suffix.lower()
            input_type = {
                "zip": "zip", "tar": "tar",
                "gz": "tar", "tgz": "tar",
            }.get(suffix, "fs")

        output_dir = opts.get("output_dir")
        if not output_dir:
            stem = target_path.name if target_path.is_dir() else target_path.stem
            output_dir = str(target_path.parent / f"{stem}_aleapp")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        return ["-t", input_type, "-i", str(target_path), "-o", output_dir]

    @classmethod
    def _env_overrides(cls) -> dict[str, str]:
        return {"BROWSER": "echo", "PYTHONUNBUFFERED": "1"}

    @classmethod
    def _parse(cls, stdout: str, stderr: str, **opts) -> dict:
        lines = stdout.splitlines()
        report_path, modules_loaded = "", ""
        for line in lines:
            low = line.lower()
            if "report location:" in low:
                report_path = line.split(":", 1)[1].strip()
            elif "modules loaded" in low:
                modules_loaded = line.strip()
        return {
            "report_location": report_path,
            "summary": modules_loaded,
            "stdout_tail": "\n".join(lines[-10:]),
        }

    # ---------- override run() to use the bundle directly ----------
    @classmethod
    def run(cls, target: str, timeout: int = 600, **opts) -> ToolResult:
        path = cls.binary_path()
        if path is None:
            return ToolResult(tool=cls.name, target=target,
                              status="not_installed", error=cls.check()[1])

        # Windows: run the exe directly. Linux/Mac: wrap the .py with python.
        if path.suffix == ".py":
            import sys
            invocation = [sys.executable, str(path)]
        else:
            invocation = [str(path)]
        invocation += cls._build_args(target, **opts)

        env = os.environ.copy()
        env.update(cls._env_overrides())

        started = time.monotonic()
        try:
            proc = subprocess.run(
                invocation, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout, check=False, env=env,
                creationflags=_no_window_flag(),
                # ALEAPP looks for its _internal/ next to the exe ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â that's
                # why we do not change cwd; the bundle resolves relative.
            )
        except subprocess.TimeoutExpired:
            return ToolResult(tool=cls.name, target=target, status="timeout",
                              command=" ".join(invocation),
                              duration_s=time.monotonic() - started,
                              error=f"Timed out after {timeout}s")

        duration = time.monotonic() - started
        stdout, stderr = proc.stdout or "", proc.stderr or ""
        if proc.returncode != 0:
            return ToolResult(tool=cls.name, target=target, status="error",
                              command=" ".join(invocation),
                              duration_s=duration,
                              raw_stdout=stdout, raw_stderr=stderr,
                              error=f"Exit code {proc.returncode}")
        return ToolResult(tool=cls.name, target=target, status="ok",
                          command=" ".join(invocation),
                          duration_s=duration,
                          output=cls._parse(stdout, stderr, **opts),
                          raw_stdout=stdout, raw_stderr=stderr)