"""Evidence file index: walk an extraction, hash and classify every file, then
answer the queries behind the Files browser (categories, folders, filters, tags,
key evidence, duplicates and hash sets).

Nothing here modifies the evidence: files are only opened for reading.
"""
from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import and_, func, or_, select, update

from .database import Case, Database, EvidenceFile, HashSet, HashSetEntry

# (key, label). "screenshots" and "camera" are views over images.
CATEGORIES = [
    ("all", "All files"), ("images", "Images"), ("audios", "Audios"),
    ("videos", "Videos"), ("screenshots", "Screenshots"), ("camera", "Camera shots"),
    ("databases", "Databases"), ("documents", "Documents"), ("plists", "Plists"),
    ("json", "JSON files"), ("archives", "Archives"), ("applications", "Applications"),
]
PRESET_TAGS = ["Of interest", "Relevant", "Irrelevant", "Follow up", "Sensitive"]

_EXT = {
    "images": {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "heif", "tif", "tiff",
               "dng", "raw", "svg"},
    "audios": {"mp3", "m4a", "aac", "wav", "ogg", "opus", "flac", "amr", "3ga", "wma"},
    "videos": {"mp4", "3gp", "mkv", "avi", "mov", "webm", "m4v", "mpg", "mpeg", "wmv"},
    "documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "odt",
                  "ods", "csv", "md", "log", "html", "htm", "xml", "vcf", "ics"},
    "databases": {"db", "sqlite", "sqlite3", "db3", "sqlitedb", "crypt12", "crypt14",
                  "crypt15", "realm"},
    "plists": {"plist"},
    "json": {"json", "jsonl"},
    "archives": {"zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "ab", "dar"},
    "applications": {"apk", "apks", "xapk", "aab", "ipa"},
}
_BY_EXT = {e: cat for cat, exts in _EXT.items() for e in exts}
_SQLITE_MAGIC = b"SQLite format 3\x00"


def classify(path: Path, ext: str) -> str:
    """Category from the extension; unknown extensions are sniffed by magic bytes."""
    if ext in _BY_EXT:
        return _BY_EXT[ext]
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return "other"
    if head.startswith(_SQLITE_MAGIC):
        return "databases"
    if head.startswith(b"bplist00"):
        return "plists"
    if head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG"):
        return "images"
    if head.startswith(b"PK\x03\x04"):
        return "archives"
    return "other"


def device_path_for(rel: str) -> str:
    """Logical acquisitions pull /sdcard/X into files/X; show the on-device path."""
    rel = rel.replace("\\", "/")
    if rel.startswith("files/"):
        return "/sdcard/" + rel[len("files/"):]
    return "/" + rel


def _dt(ts: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


_HEX = re.compile(r"\b([0-9a-fA-F]{32}|[0-9a-fA-F]{64})\b")


class EvidenceFiles:
    """Indexer + query layer over the ``evidence_files`` table."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------ indexing
    def index_tree(self, case_id: str, extraction_id: int, root: Path,
                   progress: Callable[[str, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> int:
        """(Re)index every file under ``root``. Returns the number of files indexed."""
        root = Path(root)
        single = root.is_file()           # e.g. one imported database or image
        if not (root.is_dir() or single):
            return 0
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            case_pk = case.id
            s.query(EvidenceFile).filter(
                EvidenceFile.extraction_id == extraction_id).delete()

        paths = [root] if single else [p for p in sorted(root.rglob("*")) if p.is_file()]
        if single:
            root = root.parent
        total = len(paths)
        batch: list[dict] = []
        count = 0

        def flush() -> None:
            if batch:
                with self.db.session() as s:
                    s.bulk_insert_mappings(EvidenceFile, batch)
                batch.clear()

        for i, path in enumerate(paths, 1):
            if cancelled and cancelled():
                break
            if progress and (i % 25 == 0 or i == total):
                progress(f"Indexing {i}/{total}: {path.name}", int(100 * i / max(total, 1)))
            try:
                st = path.stat()
                md5, sha = hashlib.md5(), hashlib.sha256()
                with open(path, "rb") as f:
                    while block := f.read(1024 * 1024):
                        md5.update(block)
                        sha.update(block)
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            ext = path.suffix.lower().lstrip(".")
            batch.append({
                "case_id": case_pk, "extraction_id": extraction_id, "name": path.name,
                "folder": Path(rel).parent.as_posix() if "/" in rel else "",
                "rel_path": rel, "device_path": device_path_for(rel),
                "abs_path": str(path), "ext": ext, "category": classify(path, ext),
                "mime": mimetypes.guess_type(path.name)[0] or "", "size": st.st_size,
                "sha256": sha.hexdigest(), "md5": md5.hexdigest(),
                "created": _dt(getattr(st, "st_birthtime", st.st_ctime)),
                "modified": _dt(st.st_mtime), "accessed": _dt(st.st_atime),
                "key_evidence": False, "tags": "", "note": "", "hashset_match": "",
            })
            count += 1
            if len(batch) >= 500:
                flush()
        flush()
        self.apply_hash_sets(case_id)
        return count

    def remove_extraction(self, extraction_id: int) -> None:
        with self.db.session() as s:
            s.query(EvidenceFile).filter(
                EvidenceFile.extraction_id == extraction_id).delete()

    # ------------------------------------------------------------ queries
    def _case_pk(self, s, case_id: str) -> int | None:
        case = s.scalar(select(Case).where(Case.case_id == case_id))
        return case.id if case else None

    def _scope(self, s, case_id: str | None, extraction_id: int | None):
        if extraction_id is not None:
            return [EvidenceFile.extraction_id == extraction_id]
        pk = self._case_pk(s, case_id) if case_id else None
        return [EvidenceFile.case_id == pk] if pk is not None else [EvidenceFile.id < 0]

    @staticmethod
    def _category_clause(category: str):
        if category in ("", "all"):
            return None
        if category == "images":
            return EvidenceFile.category == "images"
        if category == "screenshots":
            return and_(EvidenceFile.category == "images",
                        func.lower(EvidenceFile.rel_path).like("%screenshot%"))
        if category == "camera":
            return and_(EvidenceFile.category == "images",
                        or_(EvidenceFile.rel_path.like("%DCIM/Camera/%"),
                            EvidenceFile.rel_path.like("%/Camera/%")))
        return EvidenceFile.category == category

    def _filters(self, flt: dict) -> list:
        clauses = []
        cat = self._category_clause(flt.get("category", "all"))
        if cat is not None:
            clauses.append(cat)
        folder = flt.get("folder")
        if folder:
            clauses.append(or_(EvidenceFile.folder == folder,
                               EvidenceFile.folder.like(folder + "/%")))
        text_q = (flt.get("text") or "").strip()
        if text_q:
            like = f"%{text_q}%"
            clauses.append(or_(EvidenceFile.name.ilike(like),
                               EvidenceFile.rel_path.ilike(like),
                               EvidenceFile.tags.ilike(like),
                               EvidenceFile.note.ilike(like),
                               EvidenceFile.sha256 == text_q.lower(),
                               EvidenceFile.md5 == text_q.lower()))
        if flt.get("key_only"):
            clauses.append(EvidenceFile.key_evidence.is_(True))
        if flt.get("tag"):
            clauses.append(EvidenceFile.tags.ilike(f"%{flt['tag']}%"))
        if flt.get("ext"):
            clauses.append(EvidenceFile.ext == flt["ext"].lower().lstrip("."))
        if flt.get("min_size") is not None:
            clauses.append(EvidenceFile.size >= int(flt["min_size"]))
        if flt.get("max_size") is not None:
            clauses.append(EvidenceFile.size <= int(flt["max_size"]))
        if flt.get("date_from"):
            clauses.append(EvidenceFile.modified >= flt["date_from"])
        if flt.get("date_to"):
            clauses.append(EvidenceFile.modified <= flt["date_to"])
        if flt.get("hash_hit"):
            clauses.append(EvidenceFile.hashset_match != "")
        return clauses

    _SORT = {"name": EvidenceFile.name, "created": EvidenceFile.created,
             "modified": EvidenceFile.modified, "size": EvidenceFile.size,
             "type": EvidenceFile.ext, "path": EvidenceFile.device_path,
             "tag": EvidenceFile.tags, "key": EvidenceFile.key_evidence}

    def query(self, case_id: str | None, extraction_id: int | None = None,
              order: str = "name", desc: bool = False, limit: int = 50000,
              **flt) -> list[dict]:
        with self.db.session() as s:
            where = self._scope(s, case_id, extraction_id) + self._filters(flt)
            col = self._SORT.get(order, EvidenceFile.name)
            stmt = select(EvidenceFile).where(*where).order_by(
                col.desc() if desc else col.asc(), EvidenceFile.id).limit(limit)
            rows = s.execute(stmt).scalars().all()
            dups = self._dup_map(s, case_id, extraction_id)
            return [self._row(r, dups.get(r.sha256, 0)) for r in rows]

    def _dup_map(self, s, case_id, extraction_id) -> dict[str, int]:
        where = self._scope(s, case_id, extraction_id) + [EvidenceFile.size > 0]
        rows = s.execute(select(EvidenceFile.sha256, func.count(EvidenceFile.id))
                         .where(*where).group_by(EvidenceFile.sha256)
                         .having(func.count(EvidenceFile.id) > 1)).all()
        return {sha: n for sha, n in rows}

    @staticmethod
    def _row(r: EvidenceFile, dups: int = 0) -> dict:
        return {"id": r.id, "name": r.name, "folder": r.folder, "rel_path": r.rel_path,
                "device_path": r.device_path, "abs_path": r.abs_path, "ext": r.ext,
                "category": r.category, "mime": r.mime, "size": r.size,
                "sha256": r.sha256, "md5": r.md5, "created": r.created,
                "modified": r.modified, "accessed": r.accessed, "key": r.key_evidence,
                "tags": [t for t in r.tags.split(",") if t], "note": r.note,
                "hashset": r.hashset_match, "dups": dups, "extraction_id": r.extraction_id}

    def category_counts(self, case_id: str | None, extraction_id: int | None = None,
                        **flt) -> dict[str, int]:
        flt = {k: v for k, v in flt.items() if k != "category"}
        out = {}
        with self.db.session() as s:
            base = self._scope(s, case_id, extraction_id) + self._filters(flt)
            for key, _label in CATEGORIES:
                clause = self._category_clause(key)
                where = base + ([clause] if clause is not None else [])
                out[key] = s.scalar(select(func.count(EvidenceFile.id)).where(*where)) or 0
        return out

    def folder_counts(self, case_id: str | None, extraction_id: int | None = None
                      ) -> dict[str, int]:
        """Cumulative file count for every folder (a folder includes its children)."""
        with self.db.session() as s:
            where = self._scope(s, case_id, extraction_id)
            rows = s.execute(select(EvidenceFile.folder, func.count(EvidenceFile.id))
                             .where(*where).group_by(EvidenceFile.folder)).all()
        totals: dict[str, int] = {}
        for folder, n in rows:
            parts = folder.split("/") if folder else []
            totals[""] = totals.get("", 0) + n
            for i in range(1, len(parts) + 1):
                key = "/".join(parts[:i])
                totals[key] = totals.get(key, 0) + n
        return totals

    def totals(self, case_id: str | None, extraction_id: int | None = None) -> tuple[int, int]:
        with self.db.session() as s:
            where = self._scope(s, case_id, extraction_id)
            n, size = s.execute(select(func.count(EvidenceFile.id),
                                       func.coalesce(func.sum(EvidenceFile.size), 0))
                                .where(*where)).one()
        return int(n), int(size)

    def key_evidence_count(self, case_id: str | None, extraction_id: int | None = None) -> int:
        with self.db.session() as s:
            where = self._scope(s, case_id, extraction_id) + [EvidenceFile.key_evidence.is_(True)]
            return s.scalar(select(func.count(EvidenceFile.id)).where(*where)) or 0

    def duplicates_of(self, file_id: int) -> list[dict]:
        """Every file sharing this file's SHA-256 (including itself)."""
        with self.db.session() as s:
            ref = s.get(EvidenceFile, file_id)
            if ref is None or not ref.sha256 or ref.size == 0:
                return []
            rows = s.execute(select(EvidenceFile).where(
                EvidenceFile.case_id == ref.case_id,
                EvidenceFile.sha256 == ref.sha256).order_by(EvidenceFile.id)).scalars().all()
            return [self._row(r, len(rows)) for r in rows] if len(rows) > 1 else []

    def get(self, file_id: int) -> dict | None:
        with self.db.session() as s:
            r = s.get(EvidenceFile, file_id)
            return self._row(r) if r else None

    # ------------------------------------------------------------ mutations
    def set_key_evidence(self, ids: list[int], value: bool) -> None:
        if ids:
            with self.db.session() as s:
                s.execute(update(EvidenceFile).where(EvidenceFile.id.in_(ids))
                          .values(key_evidence=value))

    def add_tag(self, ids: list[int], tag: str) -> None:
        tag = tag.strip().replace(",", " ")
        if not tag or not ids:
            return
        with self.db.session() as s:
            for r in s.execute(select(EvidenceFile).where(
                    EvidenceFile.id.in_(ids))).scalars():
                tags = [t for t in r.tags.split(",") if t]
                if tag not in tags:
                    r.tags = ",".join(tags + [tag])

    def remove_tag(self, ids: list[int], tag: str) -> None:
        with self.db.session() as s:
            for r in s.execute(select(EvidenceFile).where(
                    EvidenceFile.id.in_(ids))).scalars():
                r.tags = ",".join(t for t in r.tags.split(",") if t and t != tag)

    def set_note(self, file_id: int, note: str) -> None:
        with self.db.session() as s:
            s.execute(update(EvidenceFile).where(EvidenceFile.id == file_id)
                      .values(note=note))

    # ------------------------------------------------------------ hash sets
    def import_hash_set(self, name: str, kind: str, path: Path) -> tuple[int, int]:
        """Read MD5/SHA-256 values (any text/CSV layout) into a new set."""
        digests = {m.group(1).lower() for m in _HEX.finditer(
            Path(path).read_text(encoding="utf-8", errors="replace"))}
        if not digests:
            raise ValueError("No MD5 or SHA-256 hashes found in that file.")
        with self.db.session() as s:
            if s.scalar(select(HashSet).where(HashSet.name == name)):
                raise ValueError(f"A hash set named '{name}' already exists.")
            hs = HashSet(name=name, kind=kind if kind in ("known", "notable") else "notable",
                         entries=len(digests))
            s.add(hs)
            s.flush()
            s.bulk_insert_mappings(HashSetEntry, [
                {"set_id": hs.id, "digest": d} for d in sorted(digests)])
            set_id = hs.id
        self.apply_hash_sets(None)          # flag matches in every existing case
        return set_id, len(digests)

    def list_hash_sets(self) -> list[dict]:
        with self.db.session() as s:
            return [{"id": h.id, "name": h.name, "kind": h.kind, "entries": h.entries,
                     "added": h.added_at.strftime("%Y-%m-%d %H:%M")}
                    for h in s.execute(select(HashSet).order_by(HashSet.id)).scalars()]

    def delete_hash_set(self, set_id: int) -> None:
        with self.db.session() as s:
            s.query(HashSetEntry).filter(HashSetEntry.set_id == set_id).delete()
            s.query(HashSet).filter(HashSet.id == set_id).delete()
        self.apply_hash_sets(None)

    def apply_hash_sets(self, case_id: str | None) -> int:
        """Flag files whose MD5/SHA-256 appears in any hash set. Returns hits."""
        with self.db.session() as s:
            lookup: dict[str, str] = {}
            for name, kind, digest in s.execute(
                    select(HashSet.name, HashSet.kind, HashSetEntry.digest)
                    .join(HashSetEntry, HashSetEntry.set_id == HashSet.id)):
                lookup[digest] = f"{name} ({kind})"
            pk = self._case_pk(s, case_id) if case_id else None
            stmt = select(EvidenceFile.id, EvidenceFile.md5, EvidenceFile.sha256,
                          EvidenceFile.hashset_match)
            if pk is not None:
                stmt = stmt.where(EvidenceFile.case_id == pk)
            updates, hits = [], 0
            for fid, md5, sha, current in s.execute(stmt):
                match = lookup.get(sha) or lookup.get(md5) or ""
                if match:
                    hits += 1
                if match != current:
                    updates.append({"id": fid, "hashset_match": match})
            if updates:
                s.bulk_update_mappings(EvidenceFile, updates)
            return hits
