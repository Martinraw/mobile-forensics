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
from dataclasses import dataclass, field
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
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(env_var)
        if sdk:
            out.append(Path(sdk) / "platform-tools" / exe)
    if platform.system() != "Windows":
        for fixed in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",
                      "/opt/platform-tools"):
            out.append(Path(fixed) / exe)
        out.append(Path.home() / "Android" / "Sdk" / "platform-tools" / exe)
        out.append(Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / exe)
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


# adb states that mean "the phone is attached" but not usable yet, with the
# fix the examiner needs to apply.
STATE_HINTS = {
    "unauthorized": "Unlock the phone and tap 'Allow' on the USB debugging prompt "
                    "(tick 'Always allow from this computer').",
    "offline": "Replug the cable, then run 'adb kill-server' and refresh.",
    "no permissions": "Linux is blocking USB access. Install the Android udev rules "
                      "(sudo apt install android-sdk-platform-tools-common) or add "
                      "your user to the plugdev group, then replug.",
    "recovery": "Phone is in recovery mode. Reboot it normally.",
    "sideload": "Phone is in sideload mode. Reboot it normally.",
    "bootloader": "Phone is in bootloader mode. Reboot it normally.",
    "untrusted": "Unlock the iPhone and tap 'Trust' when asked, then enter the passcode.",
}
_KNOWN_STATES = ("device", "offline", "unauthorized", "recovery", "sideload",
                 "bootloader", "no permissions", "host", "authorizing", "connecting")

# Details (OS version, root) are read once per serial, not on every poll.
_DETAIL_CACHE: dict[str, dict] = {}


@dataclass
class Detection:
    """Everything the GUI needs to explain the current device situation."""
    devices: list = field(default_factory=list)
    adb_ok: bool = False
    adb_where: str = ""
    ios_tools_ok: bool = False
    message: str = ""
    level: str = "idle"          # "ok" | "warn" | "error" | "idle"


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Run a command, never raise. Returns (returncode, stdout+stderr)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def hint_for(device: DeviceInfo) -> str:
    """Plain-language next step for a device that is not ready."""
    return STATE_HINTS.get(device.state, "")


def adb_devices() -> list[DeviceInfo]:
    """Android devices from ``adb devices -l`` (``[]`` if adb is missing)."""
    adb = adb_path()
    if adb is None:
        return []
    code, out = _run([str(adb), "devices", "-l"])
    if code != 0:
        return []
    return _parse_devices(out)


def _parse_devices(stdout: str) -> list[DeviceInfo]:
    """Parse the output of ``adb devices -l``.

    Handles multi-word states such as ``no permissions (...)`` and ignores
    the ``* daemon started`` chatter adb prints on first run.
    """
    out: list[DeviceInfo] = []
    for line in stdout.splitlines():
        line = line.strip()
        if (not line or line.lower().startswith("list of devices")
                or line.startswith("*") or line.startswith("adb server")):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        serial, rest = parts[0], parts[1].strip()

        state = next((s for s in sorted(_KNOWN_STATES, key=len, reverse=True)
                      if rest.lower().startswith(s)), None)
        if state is None:
            continue                      # not a device line
        rest = rest[len(state):]

        attrs = {}
        for token in rest.split():
            if ":" in token:
                k, v = token.split(":", 1)
                attrs[k] = v
        model = attrs.get("model", "unknown")
        out.append(DeviceInfo(
            serial=serial, model=model, name=model.replace("_", " "),
            product=attrs.get("product", ""), device=attrs.get("device", ""),
            transport_id=attrs.get("transport_id", ""), state=state,
        ))
    return out


def ios_devices() -> list[DeviceInfo]:
    """iPhones/iPads visible through libimobiledevice (``idevice_id -l``)."""
    if shutil.which("idevice_id") is None:
        return []
    code, out = _run(["idevice_id", "-l"])
    if code != 0:
        return []
    devices = []
    for udid in (ln.strip() for ln in out.splitlines()):
        if not re.fullmatch(r"[0-9A-Fa-f-]{20,}", udid):
            continue
        devices.append(DeviceInfo(
            serial=udid, model="iPhone", name="iPhone", platform="iOS",
            state="untrusted"))
    return devices


def _enrich_ios(dev: DeviceInfo) -> None:
    if shutil.which("ideviceinfo") is None:
        return
    info = _DETAIL_CACHE.get(dev.serial)
    if info is None:
        values = {}
        for key in ("DeviceName", "ProductType", "ProductVersion"):
            code, out = _run(["ideviceinfo", "-u", dev.serial, "-k", key], timeout=8)
            values[key] = out.strip() if code == 0 and "ERROR" not in out else ""
            if not values[key]:
                break                        # not trusted yet: skip the rest
        if not any(values.values()):
            return                           # not paired/trusted yet; don't cache
        info = values
        _DETAIL_CACHE[dev.serial] = info
    dev.state = "device"
    dev.model = info["ProductType"] or dev.model
    dev.name = info["DeviceName"] or dev.name
    dev.os_version = info["ProductVersion"]


def _enrich_android(dev: DeviceInfo, adb: Path) -> None:
    """Fill OS version / manufacturer / root flag (read-only queries)."""
    info = _DETAIL_CACHE.get(dev.serial)
    if info is None:
        def prop(key: str) -> str:
            code, out = _run([str(adb), "-s", dev.serial, "shell", "getprop", key], 6)
            return out.strip() if code == 0 else ""
        info = {
            "os": prop("ro.build.version.release"),
            "maker": prop("ro.product.manufacturer"),
            "model": prop("ro.product.model"),
        }
        code, out = _run([str(adb), "-s", dev.serial, "shell", "su", "-c", "id"], 5)
        info["rooted"] = code == 0 and "uid=0" in out
        _DETAIL_CACHE[dev.serial] = info
    dev.os_version = info["os"]
    dev.rooted = info["rooted"]
    if info["model"]:
        dev.model = info["model"]
        dev.name = f"{info['maker'].title()} {info['model']}".strip()


def connected_devices(enrich: bool = False) -> list[DeviceInfo]:
    """Android (ADB) plus iOS (libimobiledevice) devices currently attached."""
    devices = adb_devices() + ios_devices()
    if enrich:
        adb = adb_path()
        for dev in devices:
            if dev.platform == "iOS":
                _enrich_ios(dev)
            elif dev.state == "device" and adb is not None:
                _enrich_android(dev, adb)
    live = {d.serial for d in devices}
    for serial in list(_DETAIL_CACHE):
        if serial not in live:
            del _DETAIL_CACHE[serial]
    return devices


def detect(enrich: bool = True) -> Detection:
    """Full detection pass with a human-readable explanation of the result."""
    adb_ok, where = adb_available()
    ios_ok = shutil.which("idevice_id") is not None
    devices = connected_devices(enrich=enrich)
    result = Detection(devices=devices, adb_ok=adb_ok, adb_where=where,
                       ios_tools_ok=ios_ok)

    if not adb_ok and not ios_ok:
        result.level = "error"
        result.message = (
            "No device tools found. Install adb (Android: 'sudo apt install adb' "
            "or Platform-Tools) and/or libimobiledevice (iPhone), "
            "or set ADB_PATH, then press Detect.")
        return result

    ready = [d for d in devices if d.state == "device"]
    blocked = [d for d in devices if d.state != "device"]
    if ready:
        names = ", ".join(d.display_name for d in ready)
        result.level = "ok"
        result.message = f"Ready: {names}"
        if blocked:
            result.message += f"  (+{len(blocked)} not ready)"
    elif blocked:
        result.level = "warn"
        first = blocked[0]
        result.message = (f"{first.platform} device found but state is "
                          f"'{first.state}'. {hint_for(first)}".strip())
    else:
        result.level = "warn"
        result.message = (
            "No phone detected. Plug in with a data-capable USB cable, enable "
            "USB debugging (Android: Settings > Developer options), unlock the "
            "screen, choose 'File transfer' for USB mode, then press Detect.")
        if not adb_ok:
            result.message += "  (adb is not installed, so only iPhones can be found.)"
    return result


def first_ready_device() -> DeviceInfo | None:
    """First Android device in the 'device' state (used by the Tools tab)."""
    for d in adb_devices():
        if d.state == "device":
            return d
    return None


# Backwards-compat: older modules imported `Device` directly.
Device = DeviceInfo
