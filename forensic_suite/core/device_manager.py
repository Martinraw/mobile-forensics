"""Device detection (ADB / libimobiledevice) with a simulated lab bench."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Device:
    """A single connected (or simulated) mobile device."""

    name: str
    platform: str
    model: str
    os_version: str
    serial: str
    imei: str = ""
    connection: str = "USB"
    rooted: bool = False


def _adb_prop(serial: str, key: str) -> str:
    try:
        r = subprocess.run(["adb", "-s", serial, "shell", "getprop", key],
                           capture_output=True, text=True, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return r.stdout.strip()
    except Exception:
        return ""


def detect_device() -> Device | None:
    """Return the first real device found via ADB or libimobiledevice."""
    if shutil.which("adb"):
        try:
            out = subprocess.run(["adb", "devices"], capture_output=True, text=True,
                                 timeout=10, creationflags=subprocess.CREATE_NO_WINDOW).stdout
            ready = [ln.strip() for ln in out.splitlines()[1:]
                     if ln.strip().endswith("device")]
            if ready:
                serial = ready[0].split()[0]
                model = _adb_prop(serial, "ro.product.model") or "Android device"
                osv = _adb_prop(serial, "ro.build.version.release") or "?"
                rooted = "uid=0" in _adb_prop(serial, "id")
                return Device(name=model, platform="Android", model=model,
                              os_version=osv, serial=serial, rooted=rooted)
        except Exception:
            pass
    if shutil.which("ideviceinfo"):
        try:
            def get(key: str) -> str:
                r = subprocess.run(["ideviceinfo", "-k", key], capture_output=True,
                                   text=True, timeout=10,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                return r.stdout.strip()

            serial = get("UniqueDeviceID")
            if serial:
                model = get("ProductType") or "iPhone"
                imei = get("InternationalMobileEquipmentIdentity") or ""
                return Device(name=model, platform="iOS", model=model,
                              os_version=get("ProductVersion") or "?",
                              serial=serial, imei=imei)
        except Exception:
            pass
    return None


def mock_devices() -> list[Device]:
    """Simulated contraband lab bench used until real hardware is attached."""
    return [
        Device(name="Pixel 8 Pro", platform="Android", model="Pixel 8 Pro",
               os_version="14", serial="SIM-PXL8-001", imei="359204081234567"),
        Device(name="iPhone 15 Pro", platform="iOS", model="iPhone15,3",
               os_version="17.2", serial="SIM-IPH15-003", imei="359204081234568"),
        Device(name="Samsung S24 (rooted)", platform="Android", model="SM-S928B",
               os_version="14", serial="SIM-SM928-009", imei="359204081234569",
               rooted=True),
    ]


def connected_devices() -> list[Device]:
    """Real device first (if any), followed by the simulated bench."""
    real = detect_device()
    bench = [d for d in mock_devices() if not real or d.serial != real.serial]
    return ([real] if real else []) + bench