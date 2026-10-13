"""Tests for the Forensic Suite backend (indexing, parsing, hash sets, import).
Synthetic data only."""
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parent.parent / "forensic_suite"
sys.path.insert(0, str(SUITE))

from core.case_manager import CaseManager  # noqa: E402
from core.database import Database  # noqa: E402
from core.evidence_files import EvidenceFiles, classify  # noqa: E402
from core.logical_parser import parse_content_query  # noqa: E402
from core.post_process import process_extraction  # noqa: E402

SMS = ("Row: 0 _id=1, address=+260970000001, date=1700000000000, type=1, "
       "body=Hello, are you free?, date_sent=0\n"
       "Row: 1 _id=2, address=+260970000001, date=1700000100000, type=2, "
       "body=line one\nline two, with comma\n")
GETPROP = ("[ro.product.model]: [SM-TEST]\n[ro.product.manufacturer]: [samsung]\n"
           "[ro.build.version.release]: [15]\n[persist.sys.timezone]: [Africa/Lusaka]\n")


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "t.db")
    db.create_all()
    cm = CaseManager(db)
    cm.create_case("T1", "Test", "Tester", "TEST-ONLY")
    files = EvidenceFiles(db)
    out = tmp_path / "acq_logical"
    (out / "files/DCIM/Camera").mkdir(parents=True)
    (out / "files/Download").mkdir(parents=True)
    (out / "sms.txt").write_text(SMS)
    (out / "getprop.txt").write_text(GETPROP)
    (out / "packages.txt").write_text(
        "package:/data/app/~~x/com.whatsapp-1/base.apk=com.whatsapp\n")
    (out / "files/DCIM/Camera/a.jpg").write_bytes(b"\xff\xd8\xff" + b"A" * 100)
    (out / "files/DCIM/Camera/a_copy.jpg").write_bytes(b"\xff\xd8\xff" + b"A" * 100)
    (out / "files/DCIM/Screenshot_1.png").write_bytes(b"\x89PNG" + b"B" * 50)
    (out / "files/Download/notes.txt").write_text("hello")
    con = sqlite3.connect(out / "files/Download/blob")  # no extension, SQLite magic
    con.execute("create table t(x)")
    con.commit()
    con.close()
    ext_id = cm.record_extraction("T1", "SM-TEST", "logical", "complete", out_dir=str(out))
    return cm, files, ext_id, out


def test_content_query_handles_commas_and_newlines():
    rows = parse_content_query(SMS)
    assert len(rows) == 2
    assert rows[0]["body"] == "Hello, are you free?"
    assert rows[1]["body"] == "line one\nline two, with comma"


def test_pipeline_indexes_parses_and_classifies(env):
    cm, files, ext_id, out = env
    summary = process_extraction(cm, files, "T1", ext_id, out)
    assert summary["files"] == 8
    assert summary["artifacts"]["sms"] == 2 and summary["artifacts"]["apps"] == 1
    assert cm.get_extraction(ext_id)["info"]["model"] == "SM-TEST"
    counts = files.category_counts("T1", ext_id)
    assert counts["images"] == 3 and counts["camera"] == 2 and counts["screenshots"] == 1
    assert counts["databases"] == 1            # sniffed by magic bytes, no extension
    assert counts["documents"] >= 2
    rows = files.query("T1", ext_id, category="camera")
    assert rows[0]["dups"] == 2
    assert rows[0]["device_path"].startswith("/sdcard/DCIM/Camera/")
    assert len(files.duplicates_of(rows[0]["id"])) == 2


def test_reindex_does_not_duplicate(env):
    cm, files, ext_id, out = env
    process_extraction(cm, files, "T1", ext_id, out)
    process_extraction(cm, files, "T1", ext_id, out)
    assert files.totals("T1", ext_id)[0] == 8
    assert cm.artifact_counts("T1", ext_id)["sms"] == 2


def test_key_evidence_tags_notes_and_filters(env):
    cm, files, ext_id, out = env
    process_extraction(cm, files, "T1", ext_id, out)
    rows = files.query("T1", ext_id, text="notes")
    fid = rows[0]["id"]
    files.set_key_evidence([fid], True)
    files.add_tag([fid], "Of interest")
    files.add_tag([fid], "Of interest")          # idempotent
    files.set_note(fid, "seen at scene")
    got = files.query("T1", ext_id, key_only=True)
    assert [r["name"] for r in got] == ["notes.txt"]
    assert got[0]["tags"] == ["Of interest"] and got[0]["note"] == "seen at scene"
    assert files.key_evidence_count("T1", ext_id) == 1
    files.remove_tag([fid], "Of interest")
    assert files.get(fid)["tags"] == []
    assert files.query("T1", ext_id, min_size=10_000_000) == []


def test_hash_sets_flag_matches(env, tmp_path):
    cm, files, ext_id, out = env
    process_extraction(cm, files, "T1", ext_id, out)
    target = files.query("T1", ext_id, text="notes")[0]
    hashfile = tmp_path / "bad.txt"
    hashfile.write_text(f"# sample\n{target['sha256']}\nnot a hash\n")
    set_id, n = files.import_hash_set("Sample", "notable", hashfile)
    assert n == 1
    hits = files.query("T1", ext_id, hash_hit=True)
    assert [r["name"] for r in hits] == ["notes.txt"]
    assert "Sample (notable)" in hits[0]["hashset"]
    with pytest.raises(ValueError):
        files.import_hash_set("Sample", "known", hashfile)
    files.delete_hash_set(set_id)
    assert files.query("T1", ext_id, hash_hit=True) == []


def test_timeline_uses_real_events(env):
    cm, files, ext_id, out = env
    process_extraction(cm, files, "T1", ext_id, out)
    events = cm.timeline_events("T1", ext_id)
    assert any(e["category"] == "messages" for e in events)
    assert any(e["detail"].startswith("FILE modified") for e in events)


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        create table cases(id integer primary key, case_id varchar(64), title varchar(255),
            examiner varchar(255), authorization_ref varchar(255), created_at datetime, notes text);
        create table artifacts(id integer primary key, case_id integer, category varchar(64),
            timestamp datetime, sender varchar(255), recipient varchar(255), content text,
            source varchar(255));
        create table extractions(id integer primary key, case_id integer, device varchar(255),
            method varchar(64), status varchar(32), started_at datetime, finished_at datetime,
            files integer, size_bytes integer);
    """)
    con.commit()
    con.close()
    Database(path).create_all()
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("pragma table_info(extractions)")}
    assert {"out_dir", "info_json", "note"} <= cols
    assert "extraction_id" in {r[1] for r in con.execute("pragma table_info(artifacts)")}


def test_import_rejects_zip_slip(tmp_path):
    from core.acquisition_service import AcquisitionError, import_to_case
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escape.txt", "x")
    with pytest.raises(AcquisitionError):
        import_to_case(tmp_path / "cases", "T9", "Tester", "TEST", evil)
    assert not (tmp_path / "cases" / "escape.txt").exists()


def test_import_zip_is_extracted_hashed_and_indexed(tmp_path):
    from core.acquisition_service import import_to_case
    z = tmp_path / "fs.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("sdcard/DCIM/x.jpg", b"\xff\xd8\xff123")
    res = import_to_case(tmp_path / "cases", "T2", "Tester", "TEST", z)
    assert res.extracted and Path(res.index_root, "sdcard/DCIM/x.jpg").is_file()
    assert res.sha256 and res.files == 1
    assert (Path(res.case_dir) / "audit.jsonl").is_file()


def test_classify_by_extension():
    assert classify(Path("x"), "apk") == "applications"
    assert classify(Path("x"), "json") == "json"
