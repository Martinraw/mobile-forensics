"""Case CRUD, extraction history, audit entries and dashboard statistics."""
from __future__ import annotations

import getpass
import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .database import (Artifact, AuditEntry, Case, Database, DeviceProfile,
                       Extraction, ToolRun)


class CaseManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_case(self, case_id: str, title: str, examiner: str,
                    authorization: str) -> Case:
        with self.db.session() as s:
            if s.scalar(select(Case).where(Case.case_id == case_id)):
                raise ValueError(f"Case '{case_id}' already exists.")
            case = Case(case_id=case_id, title=title, examiner=examiner,
                        authorization_ref=authorization)
            s.add(case)
            s.flush()
            s.add(AuditEntry(case_id=case.id, user=getpass.getuser(),
                             action="case_created",
                             details=f"case={case_id} examiner={examiner}"))
            return case

    def list_cases(self) -> list[dict]:
        with self.db.session() as s:
            rows = s.execute(select(Case).order_by(Case.created_at.desc())).scalars().all()
            result = []
            for c in rows:
                artifacts = s.scalar(
                    select(func.count(Artifact.id)).where(Artifact.case_id == c.id)) or 0
                result.append({"case_id": c.case_id, "title": c.title,
                               "examiner": c.examiner,
                               "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                               "artifacts": artifacts})
            return result

    def get_case(self, case_id: str) -> Case | None:
        with self.db.session() as s:
            return s.scalar(select(Case).where(Case.case_id == case_id))

    def delete_case(self, case_id: str) -> bool:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                return False
            s.delete(case)
            return True

    def add_artifact(self, case_id: str, category: str, content: str,
                     sender: str = "", recipient: str = "", source: str = "",
                     timestamp: datetime | None = None) -> Artifact:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            artifact = Artifact(case_id=case.id, category=category, content=content,
                                sender=sender or None, recipient=recipient or None,
                                source=source or None,
                                timestamp=timestamp or _utcnow())
            s.add(artifact)
            return artifact

    def add_audit(self, case_id: str, action: str, details: str = "") -> None:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            s.add(AuditEntry(case_id=case.id, user=getpass.getuser(),
                             action=action, details=details))

    def recent_activity(self, limit: int = 20) -> list[dict]:
        with self.db.session() as s:
            rows = s.execute(select(AuditEntry).order_by(
                AuditEntry.time_utc.desc()).limit(limit)).scalars().all()
            case_ids = {c.id: c.case_id for c in s.scalars(select(Case)).all()}
            return [{"time": e.time_utc.strftime("%H:%M:%S"), "user": e.user,
                     "action": e.action, "details": e.details,
                     "case": case_ids.get(e.case_id, "?")} for e in rows]

    def list_extractions(self, case_id: str | None = None) -> list[dict]:
        with self.db.session() as s:
            stmt = select(Extraction).order_by(Extraction.id.desc())
            if case_id:
                case = s.scalar(select(Case).where(Case.case_id == case_id))
                if case is None:
                    return []
                stmt = stmt.where(Extraction.case_id == case.id)
            case_ids = {c.id: c.case_id for c in s.scalars(select(Case)).all()}
            return [self._extraction_dict(e, case_ids) for e in s.execute(stmt).scalars()]

    @staticmethod
    def _extraction_dict(e: Extraction, case_ids: dict) -> dict:
        fmt = "%Y-%m-%d %H:%M:%S"
        try:
            info = json.loads(e.info_json or "{}")
        except ValueError:
            info = {}
        return {"id": e.id, "case": case_ids.get(e.case_id, "?"), "device": e.device,
                "method": e.method, "status": e.status,
                "started": e.started_at.strftime(fmt) if e.started_at else "-",
                "finished": e.finished_at.strftime(fmt) if e.finished_at else "-",
                "files": e.files, "size_bytes": e.size_bytes, "out_dir": e.out_dir or "",
                "info": info, "note": e.note or ""}

    def get_extraction(self, extraction_id: int) -> dict | None:
        with self.db.session() as s:
            e = s.get(Extraction, extraction_id)
            if e is None:
                return None
            case_ids = {c.id: c.case_id for c in s.scalars(select(Case)).all()}
            return self._extraction_dict(e, case_ids)

    def record_extraction(self, case_id: str, device: str, method: str,
                          status: str, files: int = 0, size_bytes: int = 0,
                          out_dir: str = "", info: dict | None = None) -> int:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            now = _utcnow()
            row = Extraction(case_id=case.id, device=device, method=method,
                             status=status, started_at=now,
                             finished_at=None if status == "running" else now,
                             files=files, size_bytes=size_bytes, out_dir=out_dir,
                             info_json=json.dumps(info or {}, ensure_ascii=False))
            s.add(row)
            s.flush()
            return row.id

    def update_extraction_info(self, extraction_id: int, **fields) -> None:
        """Merge keys into the extraction's info (owner, incident number, ...)."""
        with self.db.session() as s:
            e = s.get(Extraction, extraction_id)
            if e is None:
                return
            try:
                info = json.loads(e.info_json or "{}")
            except ValueError:
                info = {}
            info.update(fields)
            e.info_json = json.dumps(info, ensure_ascii=False)

    def set_extraction_note(self, extraction_id: int, note: str) -> None:
        with self.db.session() as s:
            e = s.get(Extraction, extraction_id)
            if e is not None:
                e.note = note

    def delete_extraction_records(self, extraction_id: int) -> None:
        """Remove the database records only. Evidence on disk is never deleted."""
        from .database import EvidenceFile
        with self.db.session() as s:
            s.query(EvidenceFile).filter(EvidenceFile.extraction_id == extraction_id).delete()
            s.query(Artifact).filter(Artifact.extraction_id == extraction_id).delete()
            e = s.get(Extraction, extraction_id)
            if e is not None:
                s.delete(e)

    # ---- artifacts tied to an extraction ----
    _LOGICAL_CATEGORIES = ("sms", "calls", "contacts", "calendar", "apps")

    def replace_artifacts(self, case_id: str, extraction_id: int, rows: list[dict],
                          category: str | None = None) -> int:
        """Replace this extraction's parsed artifacts (so re-parsing never duplicates)."""
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            cats = {category} if category else set(self._LOGICAL_CATEGORIES)
            cats |= {r["category"] for r in rows}
            s.query(Artifact).filter(Artifact.extraction_id == extraction_id,
                                     Artifact.category.in_(cats)).delete(
                synchronize_session=False)
            s.bulk_insert_mappings(Artifact, [
                {"case_id": case.id, "extraction_id": extraction_id,
                 "category": r["category"], "timestamp": r.get("timestamp"),
                 "sender": r.get("sender") or None, "recipient": r.get("recipient") or None,
                 "content": r.get("content"), "source": (r.get("source") or "")[:255] or None}
                for r in rows])
        return len(rows)

    def artifact_counts(self, case_id: str, extraction_id: int | None = None) -> dict[str, int]:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                return {}
            stmt = select(Artifact.category, func.count(Artifact.id)).where(
                Artifact.case_id == case.id)
            if extraction_id is not None:
                stmt = stmt.where(Artifact.extraction_id == extraction_id)
            return dict(s.execute(stmt.group_by(Artifact.category)).all())

    def timeline_events(self, case_id: str, extraction_id: int | None = None,
                        limit: int = 20000) -> list[dict]:
        """Real dated events: dated artifacts plus file modification times."""
        from .database import EvidenceFile
        events: list[dict] = []
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                return []
            stmt = select(Artifact).where(Artifact.case_id == case.id,
                                          Artifact.timestamp.is_not(None))
            if extraction_id is not None:
                stmt = stmt.where(Artifact.extraction_id == extraction_id)
            for a in s.execute(stmt.limit(limit)).scalars():
                label = {"sms": "messages", "whatsapp": "messages"}.get(a.category, a.category)
                who = a.sender or a.recipient or ""
                events.append({"ts": a.timestamp, "category": label,
                               "detail": f"{a.category.upper()} {who}: {(a.content or '')[:160]}"})
            fstmt = select(EvidenceFile).where(
                EvidenceFile.case_id == case.id, EvidenceFile.modified.is_not(None),
                EvidenceFile.category.in_(("images", "videos", "audios", "documents")))
            if extraction_id is not None:
                fstmt = fstmt.where(EvidenceFile.extraction_id == extraction_id)
            for f in s.execute(fstmt.limit(limit)).scalars():
                events.append({"ts": f.modified, "category": "media" if f.category in
                               ("images", "videos", "audios") else "documents",
                               "detail": f"FILE modified: {f.device_path}"})
        events.sort(key=lambda e: e["ts"])
        return events[-limit:]

    def case_tree(self) -> list[dict]:
        """Cases with their extractions, for the explorer."""
        cases = []
        for c in self.list_cases():
            cases.append({**c, "extractions": self.list_extractions(c["case_id"])})
        return cases

    def add_tool_run(self, case_id: str, tool: str, target: str,
                     status: str, command: str = "", duration_s: float = 0.0,
                     output: dict | None = None) -> ToolRun:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            run = ToolRun(
                case_id=case.id, tool=tool, target=target, status=status,
                command=command, duration_s=duration_s,
                output_json=json.dumps(output or {}, ensure_ascii=False),
            )
            s.add(run)
            s.flush()
            s.add(AuditEntry(case_id=case.id, user=getpass.getuser(),
                             action="tool_run",
                             details=f"tool={tool} target={target} status={status}"))
            return run

    def list_tool_runs(self, case_id: str | None = None) -> list[dict]:
        with self.db.session() as s:
            stmt = select(ToolRun).order_by(ToolRun.started_at.desc())
            if case_id:
                case = s.scalar(select(Case).where(Case.case_id == case_id))
                if case is None:
                    return []
                stmt = stmt.where(ToolRun.case_id == case.id)
            rows = s.execute(stmt).scalars().all()
            return [{"tool": r.tool, "target": r.target, "status": r.status,
                     "started": r.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                     "duration_s": round(r.duration_s, 2),
                     "output": json.loads(r.output_json or "{}")} for r in rows]

    def stats(self) -> dict:
        with self.db.session() as s:
            cases = s.scalar(select(func.count(Case.id))) or 0
            devices = s.scalar(select(func.count(Extraction.id)).where(
                Extraction.status == "complete")) or 0
            data_bytes = s.scalar(select(func.coalesce(func.sum(Extraction.size_bytes), 0))) or 0
            active = s.scalar(select(func.count(Extraction.id)).where(
                Extraction.status == "running")) or 0
            categories = dict(s.execute(
                select(Artifact.category, func.count(Artifact.id)).group_by(
                    Artifact.category)).all())
            platforms = dict(s.execute(
                select(DeviceProfile.platform, func.count(DeviceProfile.id)).group_by(
                    DeviceProfile.platform)).all())
            activity = self._activity(s, days=7)
        return {
            "cases": cases, "devices": devices,
            "data_bytes": data_bytes,
            "data_gb": round(data_bytes / (1024 ** 3), 1),
            "active_tasks": active,
            "categories": categories,
            "platforms": platforms,
            "activity": activity,
        }

    @staticmethod
    def _activity(s, days: int) -> list[tuple[str, int]]:
        cutoff = _utcnow() - timedelta(days=days)
        rows = s.execute(
            select(func.date(Artifact.timestamp), func.count(Artifact.id))
            .where(Artifact.timestamp >= cutoff)
            .group_by(func.date(Artifact.timestamp))).all()
        counts = dict(rows)
        result = []
        for i in range(days - 1, -1, -1):
            day = (_utcnow() - timedelta(days=i)).date()
            result.append((day.isoformat(), counts.get(day.isoformat(), 0)))
        return result

    def seed_demo(self) -> None:
        with self.db.session() as s:
            if s.scalar(select(func.count(Case.id))):
                return
            demo = Case(case_id="DEMO001", title="Synthetic demo case",
                        examiner="analyst", authorization_ref="SIM-TEST-ONLY")
            s.add(demo)
            s.flush()
            s.add_all([
                DeviceProfile(name="Pixel 8 Pro", platform="Android",
                              model="Pixel 8 Pro", os_version="14",
                              serial="SIM-PXL8-001", imei="359204081234567"),
                DeviceProfile(name="iPhone 15 Pro", platform="iOS",
                              model="iPhone15,3", os_version="17.2",
                              serial="SIM-IPH15-003", imei="359204081234568"),
            ])
            s.add(Extraction(case_id=demo.id, device="Pixel 8 Pro",
                             method="Logical + FS", status="complete",
                             started_at=_utcnow() - timedelta(days=3),
                             finished_at=_utcnow() - timedelta(days=3),
                             files=12486, size_bytes=3_400_000_000))
            samples = {
                "sms": ["Hi, are we meeting tomorrow?", "Yes 10am at the cafe",
                        "Got the package, sending the files", "Call me when free"],
                "calls": ["+260 97 123 4567", "+260 96 765 4321", "+260 77 555 1212"],
                "contacts": ["Alice Mwamba", "Brian Tembo", "Carol Banda"],
                "media": ["IMG_20240201.jpg", "VID_20240203.mp4", "IMG_20240205.jpg"],
                "locations": ["-15.3875, 28.3228", "-15.4214, 28.2873"],
                "apps": ["WhatsApp v2.24.1", "Telegram v10.3", "Instagram v328"],
                "cloud": ["Drive: case_notes.pdf", "Drive: backup_0211.zip"],
                "deleted": ["Recovered msg #1", "Recovered msg #2", "Thumbnail cache"],
            }
            for category, items in samples.items():
                for item in items:
                    ts = _utcnow() - timedelta(days=random.randint(0, 6),
                                              hours=random.randint(0, 23))
                    s.add(Artifact(case_id=demo.id, category=category, content=item,
                                   sender="Contact", recipient="DEVICE_OWNER",
                                   source=f"/data/{category}/file.db", timestamp=ts))
            s.add(AuditEntry(case_id=demo.id, user="analyst", action="demo_seeded",
                             details="synthetic data for development"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)