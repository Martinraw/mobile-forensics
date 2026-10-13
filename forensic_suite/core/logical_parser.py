"""Turn the raw output of a logical acquisition into case artifacts.

Android's ``content query`` prints one ``Row: N key=value, key=value`` record per
line. Values may themselves contain ", " and newlines, so records are re-joined
and split only where the next ``name=`` token begins. Parsing is best-effort and
read-only: the original ``*.txt`` files are never modified.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_ROW = re.compile(r"^Row: \d+ ")
_FIELD_SPLIT = re.compile(r", (?=[A-Za-z_][A-Za-z0-9_.]*=)")
_PROP = re.compile(r"^\[(.+?)\]: \[(.*)\]$")

CALL_TYPES = {"1": "Incoming", "2": "Outgoing", "3": "Missed", "4": "Voicemail",
              "5": "Rejected", "6": "Blocked"}


def parse_content_query(text: str) -> list[dict]:
    rows: list[str] = []
    for line in text.splitlines():
        if _ROW.match(line):
            rows.append(line)
        elif rows:                       # continuation of a multi-line value
            rows[-1] += "\n" + line
    parsed = []
    for raw in rows:
        body = _ROW.sub("", raw, count=1)
        record = {}
        for part in _FIELD_SPLIT.split(body):
            key, _, value = part.partition("=")
            record[key.strip()] = "" if value == "NULL" else value
        parsed.append(record)
    return parsed


def _ts(value: str, seconds: bool = False) -> datetime | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if not seconds:
        n /= 1000
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def parse_getprop(text: str) -> dict[str, str]:
    props = {}
    for line in text.splitlines():
        m = _PROP.match(line.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return props


def device_details(out_dir: Path) -> dict:
    """Device facts for the overview page, from getprop.txt when present."""
    path = Path(out_dir) / "getprop.txt"
    if not path.is_file():
        return {}
    p = parse_getprop(path.read_text(encoding="utf-8", errors="replace"))
    tz = p.get("persist.sys.timezone", "")
    return {k: v for k, v in {
        "vendor": p.get("ro.product.manufacturer", ""),
        "model": p.get("ro.product.model", ""),
        "os_version": p.get("ro.build.version.release", ""),
        "security_patch": p.get("ro.build.version.security_patch", ""),
        "fingerprint": p.get("ro.build.fingerprint", ""),
        "chipset": p.get("ro.hardware.chipname") or p.get("ro.board.platform", ""),
        "build_id": p.get("ro.build.display.id", ""),
        "timezone": tz,
        "sim_country": p.get("gsm.sim.operator.iso-country", ""),
        "sim_operator_code": p.get("gsm.sim.operator.numeric", ""),
        "sim_operator": p.get("gsm.sim.operator.alpha", ""),
        "language": p.get("persist.sys.locale") or p.get("ro.product.locale", ""),
        "serial": p.get("ro.serialno", ""),
    }.items() if v}


def parse_logical(case_manager, case_id: str, extraction_id: int, out_dir: Path) -> dict[str, int]:
    """Create artifacts for every recognised file in a logical acquisition."""
    out_dir = Path(out_dir)
    rows: list[dict] = []

    def read(name: str) -> str:
        p = out_dir / name
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""

    for r in parse_content_query(read("sms.txt")):
        sent = r.get("type") == "2"
        addr = r.get("address", "")
        rows.append(dict(category="sms", timestamp=_ts(r.get("date", "")),
                         sender="DEVICE_OWNER" if sent else addr,
                         recipient=addr if sent else "DEVICE_OWNER",
                         content=r.get("body", ""), source="sms.txt"))
    for r in parse_content_query(read("mms.txt")):
        rows.append(dict(category="sms", timestamp=_ts(r.get("date", ""), seconds=True),
                         sender=r.get("address", ""), recipient="",
                         content="[MMS] " + (r.get("sub", "") or r.get("ct_t", "")),
                         source="mms.txt"))
    for r in parse_content_query(read("call_log.txt")):
        kind = CALL_TYPES.get(r.get("type", ""), r.get("type", ""))
        name = r.get("name", "")
        rows.append(dict(category="calls", timestamp=_ts(r.get("date", "")),
                         sender=r.get("number", ""),
                         recipient=f"{kind} ({r.get('duration', '0')}s)",
                         content=f"{kind} {r.get('number', '')} {name}".strip(),
                         source="call_log.txt"))
    for r in parse_content_query(read("contacts.txt")):
        name, number = r.get("display_name", ""), r.get("data1", "") or r.get("number", "")
        rows.append(dict(category="contacts", timestamp=None, sender=name,
                         recipient=number, content=f"{name} {number}".strip(),
                         source="contacts.txt"))
    for r in parse_content_query(read("calendar.txt")):
        rows.append(dict(category="calendar", timestamp=_ts(r.get("dtstart", "")),
                         sender="", recipient="",
                         content=" - ".join(x for x in (r.get("title", ""),
                                                        r.get("eventLocation", "")) if x),
                         source="calendar.txt"))
    for line in read("packages.txt").splitlines():
        if line.startswith("package:") and "=" in line:
            path, _, pkg = line[len("package:"):].rpartition("=")
            rows.append(dict(category="apps", timestamp=None, sender="", recipient="",
                             content=pkg.strip(), source=path))

    case_manager.replace_artifacts(case_id, extraction_id, rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return counts


def parse_whatsapp_db(case_manager, case_id: str, extraction_id: int, db_path: Path) -> int:
    """Parse an unencrypted msgstore.db (on a temporary copy, never the evidence)."""
    from core.acquisition_service import REPO_ROOT  # noqa: F401  (adds repo root to sys.path)
    from mobileforensics.whatsapp_parser import parse_messages

    db_path = Path(db_path)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "msgstore.db"
        shutil.copy2(db_path, work)
        for suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + suffix)
            if side.is_file():
                shutil.copy2(side, Path(str(work) + suffix))
        rows = []
        for m in parse_messages(work):
            rows.append(dict(
                category="whatsapp",
                timestamp=(datetime.fromisoformat(m["timestamp_utc"]).replace(tzinfo=None)
                           if m["timestamp_utc"] else None),
                sender="DEVICE_OWNER" if m["from_me"] else (m["sender"] or m["chat"] or ""),
                recipient=m["chat"] or "", content=m["text"] or "",
                source=f"msgstore.db#{m['source_table']}:{m['source_rowid']}"))
    case_manager.replace_artifacts(case_id, extraction_id, rows, category="whatsapp")
    return len(rows)
