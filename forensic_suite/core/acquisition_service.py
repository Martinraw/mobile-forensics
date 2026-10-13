"""Bridge between the Qt GUI and the real acquisition engine in ``mobileforensics/``.

Runs a genuine acquisition (adb / libimobiledevice), hashes and verifies the result,
and writes the tamper-evident audit log inside a case folder. Nothing here is simulated.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The engine lives one level above forensic_suite/ in the repository.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mobileforensics.acquisition import (AcquisitionCancelled,  # noqa: E402
                                         AcquisitionError, AcquisitionManager,
                                         Control, DeviceInfo as EngineDevice,
                                         Method)
from mobileforensics.evidence import AuditLog, CaseRecord  # noqa: E402

from core.device_manager import adb_path  # noqa: E402

CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
METHOD_BY_NAME = {m.value: m for m in Method}


@dataclass
class AcquisitionRequest:
    cases_root: Path
    case_id: str
    examiner: str
    authorization: str
    device: object                   # core.device_manager.DeviceInfo
    methods: list[str]               # "logical" | "backup" | "filesystem"
    verify: bool = True
    selection: set | None = None     # DATA_ITEMS keys; None = everything


@dataclass
class MethodResult:
    method: str
    status: str                      # complete | partial | failed | cancelled
    out_dir: str = ""
    files: int = 0
    size_bytes: int = 0
    manifest: str = ""
    manifest_sha256: str = ""
    verified: bool | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class AcquisitionOutcome:
    ok: bool
    case_dir: str = ""
    results: list[MethodResult] = field(default_factory=list)
    message: str = ""
    cancelled: bool = False


def plan_methods(device, chk_full: bool, chk_logical: bool, chk_backup: bool):
    """Map the UI checkboxes to engine methods for this device.

    Returns ``(methods, problem)``; ``problem`` explains why nothing can run.
    """
    platform = device.platform.lower()
    methods: list[str] = []
    if platform == "android":
        if chk_logical:
            methods.append("logical")
        if chk_full:
            if not device.rooted:
                return [], ("Full file-system needs a rooted, authorized test device. "
                            "This phone is not rooted. For a locked phone, import an "
                            "image made by another tool instead.")
            methods.append("filesystem")
        if chk_backup and not methods:
            return [], ("Backup acquisition is iOS-only. Use Logical for this "
                        "Android device.")
    else:  # iOS
        if chk_full and not (chk_logical or chk_backup):
            return [], ("Full file-system acquisition of an iPhone needs a "
                        "jailbreak or an image from another tool. "
                        "Choose Backup instead.")
        if chk_logical or chk_backup:
            methods.append("backup")
    if not methods:
        return [], "Select at least one extraction method."
    return methods, ""


def _ensure_case_dir(root: Path, case_id: str, examiner: str, authorization: str) -> Path:
    if not CASE_ID_RE.match(case_id or ""):
        raise AcquisitionError(
            "Case ID may only contain letters, digits, - and _ (max 64 characters).")
    if not examiner.strip() or not authorization.strip():
        raise AcquisitionError("Examiner and authorization reference are both required.")
    case_dir = Path(root).expanduser() / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    if not (case_dir / "case.json").exists():
        CaseRecord(case_id, examiner.strip(), authorization.strip()).save(case_dir)
        AuditLog(case_dir / "audit.jsonl").log(
            "case_created", case_id=case_id, examiner=examiner.strip(),
            authorization=authorization.strip())
    return case_dir


def run_acquisition(request: AcquisitionRequest, on_progress=None,
                    is_cancelled=None) -> AcquisitionOutcome:
    """Perform the acquisition. Blocking: call from a worker thread."""
    adb = adb_path()
    if adb is not None:  # engine calls plain "adb"; make sure it resolves
        os.environ["PATH"] = str(adb.parent) + os.pathsep + os.environ.get("PATH", "")

    try:
        case_dir = _ensure_case_dir(request.cases_root, request.case_id,
                                    request.examiner, request.authorization)
    except (AcquisitionError, OSError) as exc:
        return AcquisitionOutcome(ok=False, message=str(exc))

    audit = AuditLog(case_dir / "audit.jsonl")
    dev = request.device
    audit.log("acquisition_requested", via="forensic_suite_gui",
              selection=sorted(request.selection) if request.selection else "all",
              authorization_confirmed_by_examiner=True,
              authorization=request.authorization, serial=dev.serial,
              methods=request.methods)
    info = EngineDevice(dev.platform.lower(), dev.serial, dev.model,
                        dev.os_version or "", bool(dev.rooted))
    manager = AcquisitionManager(case_dir, audit)
    ctl = Control(on_progress, is_cancelled)
    requested = {METHOD_BY_NAME[m] for m in request.methods}

    message, cancelled, ok = "", False, True
    try:
        manager.acquire(info, requested, ctl, verify=request.verify,
                        selection=request.selection)
    except AcquisitionCancelled:
        message, cancelled, ok = "Extraction cancelled. Partial data was kept and hashed.", True, False
    except AcquisitionError as exc:
        message, ok = str(exc), False

    results = [MethodResult(
        method=row["method"].value, status=row["status"], out_dir=str(row["out"]),
        files=row["files"], size_bytes=row["size_bytes"],
        manifest=str(row["manifest"] or ""), manifest_sha256=row["manifest_sha256"],
        verified=row.get("verified"), errors=list(row["errors"]),
    ) for row in manager.report]
    if ok:
        message = "Extraction complete. Evidence hashed, verified and logged."
        if any(r.status == "partial" for r in results):
            message = ("Extraction finished with warnings. Some sources were "
                       "unavailable; see acquisition_errors.txt.")
    return AcquisitionOutcome(ok=ok, case_dir=str(case_dir), results=results,
                              message=message, cancelled=cancelled)



# ---------------------------------------------------------------- import
import json  # noqa: E402
import tarfile  # noqa: E402
import zipfile  # noqa: E402

from mobileforensics.acquisition import import_evidence  # noqa: E402
from mobileforensics.evidence import sha256_file, utc_now  # noqa: E402


@dataclass
class ImportOutcome:
    case_dir: str
    imported: str        # copy of the original inside the case
    index_root: str      # folder to index (the copy, or its extracted contents)
    sha256: str = ""     # of the original file ("" for folders)
    files: int = 0
    size_bytes: int = 0
    extracted: bool = False


def _safe_extract(archive: Path, dest: Path) -> None:
    """Extract zip/tar without allowing members to escape ``dest`` (zip-slip)."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()

    def check(name: str) -> None:
        target = (dest / name).resolve()
        if root != target and root not in target.parents:
            raise AcquisitionError(f"Archive member escapes the target folder: {name}")

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                check(n)
            z.extractall(dest)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as t:
            members = t.getmembers()
            for m in members:
                check(m.name)
                if m.issym() or m.islnk() or m.isdev():
                    raise AcquisitionError(f"Refusing special archive member: {m.name}")
            t.extractall(dest, members=members)
    else:
        raise AcquisitionError("Not a zip or tar archive.")


def import_to_case(cases_root: Path, case_id: str, examiner: str, authorization: str,
                   source: Path, on_progress=None) -> ImportOutcome:
    """Import an image/backup/folder made by another tool into a case.

    The original is copied (hash-checked) into ``<case>/imported``; zip and tar
    archives are additionally extracted for indexing. Everything is audited and a
    SHA-256 manifest is written.
    """
    source = Path(source).expanduser()
    if not source.exists():
        raise AcquisitionError(f"Source not found: {source}")
    case_dir = _ensure_case_dir(Path(cases_root), case_id, examiner, authorization)
    audit = AuditLog(case_dir / "audit.jsonl")
    if on_progress:
        on_progress(f"Copying {source.name}", 5)
    dest = import_evidence(source, case_dir, audit)
    index_root, extracted = dest, False
    original_sha = ""
    if dest.is_file():
        original_sha = sha256_file(dest)
        if zipfile.is_zipfile(dest) or tarfile.is_tarfile(dest):
            if on_progress:
                on_progress(f"Extracting {dest.name}", 40)
            index_root = dest.parent / (dest.name + "_extracted")
            _safe_extract(dest, index_root)
            extracted = True
            audit.log("evidence_extracted", archive=str(dest), to=str(index_root))
    manifest = case_dir / f"{dest.name}.manifest.json"
    from mobileforensics.evidence import build_manifest
    if dest.is_dir() or extracted:
        build_manifest(index_root, manifest)
    else:
        manifest.write_text(json.dumps({"created_utc": utc_now(), "root": str(dest.parent),
                                        "files": {dest.name: {"sha256": original_sha,
                                                              "size": dest.stat().st_size}}},
                                       indent=2))
    data = json.loads(manifest.read_text())
    audit.log("manifest_written", method="import", path=str(manifest),
              sha256=sha256_file(manifest), files=len(data["files"]))
    return ImportOutcome(
        case_dir=str(case_dir), imported=str(dest), index_root=str(index_root),
        sha256=original_sha, files=len(data["files"]),
        size_bytes=sum(f["size"] for f in data["files"].values()), extracted=extracted)
