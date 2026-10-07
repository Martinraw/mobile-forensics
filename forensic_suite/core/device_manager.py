"""Live-device discovery via ADB (Android Debug Bridge).

Locates ``adb.exe`` in this order:

  1. ``ADB_PATH`` environment variable (folder containing adb)
  2. System ``PATH`` via ``shutil.which("adb")``
  3. Winget's local package folder glob
  4. Common manual install paths (``C:\\platform-tools``, ``%USERPROFILE%\\platform-tools``)

Then parses ``adb devices -l`` output into dicts the GUI can render.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


@dataclass
class DeviceInfo:
    """One ADB-visible device.

    Fields marked "extra" are populated from the old DeviceProfile schema or
    set to safe defaults so existing GUI code keeps working.
    """
    serial: str
    model: str
    product: str = ""
    device: str = ""
    transport_id: str = ""
    state: str = "device"        # "device" (ready), "unauthorized", "offline"

    # --- extra fields used by the Extraction tab / DeviceCard widget ---
    name: str = ""               # human label (falls back to model)
    platform: str = "Android"    # ADB only sees Android; iOS uses usbmux
    os_version: str = ""         # fetched lazily via `adb shell getprop`
    imei: str = ""               # requires root / special access
    connection: str = "USB"
    rooted: bool = False         # heuristic; True if `adb shell su -c id` works
    last_seen: object = None     # datetime, filled in by callers if desired

    @property
    def display_name(self) -> str:
        label = self.name or self.model.replace("_", " ")
        return f"{label} ({self.serial})"


def _adb_candidates() -> list[Path]:
    """All plausible locations of the adb executable, in priority order."""
    exe = "adb.exe" if platform.system() == "Windows" else "adb"
    out: list[Path] = []

    # 1. ADB_PATH env var
    env_path = os.environ.get("ADB_PATH")
    if env_path:
        out.append(Path(env_path) / exe)

    # 2. System PATH
    found = shutil.which("adb")
    if found:
        out.append(Path(found))

    # 3. Winget packages glob
    if platform.system() == "Windows":
        winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.is_dir():
            for p in winget_root.glob("Google.PlatformTools_*/platform-tools/" + exe):
                out.append(p)

    # 4. Common manual locations
    out.append(Path("C:/platform-tools") / exe)
    out.append(Path.home() / "platform-tools" / exe)
    out.append(Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / exe)

    return out


def adb_path() -> Path | None:
    """Return the first existing adb executable, or None."""
    for candidate in _adb_candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def adb_available() -> tuple[bool, str]:
    """``(installed, where_or_reason)`` for the Tools tab status bar."""
    path = adb_path()
    if path is None:
        return False, (
            "adb not found. Install Android Platform-Tools "
            "(winget install Google.PlatformTools) or set ADB_PATH."
        )
    return True, str(path)


def connected_devices() -> list[DeviceInfo]:
    """Run ``adb devices -l`` and return parsed devices.

    Returns ``[]`` cleanly if adb is missing or the command fails.
    """
    adb = adb_path()
    if adb is None:
        return []

    try:
        proc = subprocess.run(
            [str(adb), "devices", "-l"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=10, check=False,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if proc.returncode != 0:
        return []

    return _parse_devices(proc.stdout or "")


def _parse_devices(stdout: str) -> list[DeviceInfo]:
    """Parse the tabular output of ``adb devices -l``."""
    out: list[DeviceInfo] = []
    # Skip the "List of devices attached" header and blank lines.
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue

        # Format: <serial> <state> [key:value ...]
        parts = re.split(r"\s+", line)
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        attrs = {}
        for token in parts[2:]:
            if ":" in token:
                k, v = token.split(":", 1)
                attrs[k] = v

        out.append(DeviceInfo(
            serial=serial,
            model=attrs.get("model", "unknown"),
            name=attrs.get("model", "unknown").replace("_", " "),
            product=attrs.get("product", ""),
            device=attrs.get("device", ""),
            transport_id=attrs.get("transport_id", ""),
            state=state,
        ))
    return out


def first_ready_device() -> DeviceInfo | None:
    """Return the first device in the 'device' state (ready for commands)."""
    for d in connected_devices():
        if d.state == "device":
            return d
    return None

# Backwards-compat: older modules imported `Device` directly.
Device = DeviceInfo
