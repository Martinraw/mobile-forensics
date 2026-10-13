"""Everything that happens after evidence lands in a case: device details, artifact
parsing, file indexing and hash-set matching. Runs on a worker thread."""
from __future__ import annotations

from pathlib import Path

from core.logical_parser import device_details, parse_logical, parse_whatsapp_db


def process_extraction(case_manager, files, case_id: str, extraction_id: int,
                       root: Path, progress=None, cancelled=None) -> dict:
    """Index and parse one extraction. ``progress(message, percent)`` is optional."""
    say = progress or (lambda _m, _p: None)
    root = Path(root)
    summary: dict = {"files": 0, "artifacts": {}, "whatsapp": 0, "hash_hits": 0}

    say("Reading device details", 2)
    details = device_details(root)
    if details:
        case_manager.update_extraction_info(extraction_id, **details)

    say("Parsing logical data", 5)
    try:
        summary["artifacts"] = parse_logical(case_manager, case_id, extraction_id, root)
    except Exception as exc:  # parsing is best-effort; never lose the extraction
        summary["parse_error"] = str(exc)

    summary["files"] = files.index_tree(
        case_id, extraction_id, root,
        progress=lambda m, p: say(m, 10 + int(p * 0.8)), cancelled=cancelled)

    say("Looking for WhatsApp databases", 92)
    for row in files.query(case_id, extraction_id, text="msgstore.db", category="databases"):
        if row["name"].lower() == "msgstore.db":
            try:
                summary["whatsapp"] += parse_whatsapp_db(
                    case_manager, case_id, extraction_id, Path(row["abs_path"]))
            except Exception as exc:
                summary.setdefault("whatsapp_errors", []).append(f"{row['rel_path']}: {exc}")
    summary["hash_hits"] = files.apply_hash_sets(case_id)
    say("Done", 100)
    return summary
