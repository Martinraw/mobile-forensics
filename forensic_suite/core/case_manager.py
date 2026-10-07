"""Case CRUD, extraction history, audit entries and dashboard statistics."""
from __future__ import annotations

import getpass
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .database import (Artifact, AuditEntry, Case, Database, DeviceProfile,
                       Extraction)


class CaseManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---------- cases ----------
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

# ---------- artifacts / audit ----------
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

    # ---------- extractions ----------
    def list_extractions(self) -> list[dict]:
        with self.db.session() as s:
            rows = s.execute(select(Extraction).order_by(Extraction.id.desc())).scalars().all()
            return [{"id": e.id, "device": e.device, "method": e.method,
                     "status": e.status,
                     "started": e.started_at.strftime("%Y-%m-%d %H:%M:%S") if e.started_at else "—",
                     "finished": e.finished_at.strftime("%Y-%m-%d %H:%M:%S") if e.finished_at else "—",
                     "files": e.files, "size_bytes": e.size_bytes} for e in rows]

    def record_extraction(self, case_id: str, device: str, method: str,
                          status: str, files: int = 0, size_bytes: int = 0) -> None:
        with self.db.session() as s:
            case = s.scalar(select(Case).where(Case.case_id == case_id))
            if case is None:
                raise ValueError(f"Unknown case '{case_id}'.")
            now = _utcnow()
            s.add(Extraction(case_id=case.id, device=device, method=method,
                             status=status, started_at=now,
                             finished_at=None if status == "running" else now,
                             files=files, size_bytes=size_bytes))

# ---------- dashboard statistics ----------
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
            "cases": cases,
            "devices": devices,
            "data_bytes": data_bytes,
            "data_gb": round(data_bytes / (1024 ** 3), 1),
            "active_tasks": active,
            "categories": categories,
            "platforms": platforms if platforms else {"Android": 2, "iOS": 1},
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

    # ---------- demo data ----------
    def seed_demo(self) -> None:
        """Populate a small synthetic dataset so the dashboard is alive."""
        with self.db.session() as s:
            if s.scalar(select(func.count(Case.id))):
                return  # already seeded
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
                "sms": ["Hi, are we meeting tomorrow?", "Yes 10am at the café",
                        "Got the package, sending the files", "Call me when free"],
                "calls": ["+260 97 123 4567", "+260 96 765 4321", "+260 77 555 1212"],
                "contacts": ["Alice Mwamba", "Brian Tembo", "Carol Banda"],
                "media": ["IMG_20240201.jpg", "VID_20240203.mp4", "IMG_20240205.jpg"],
                "locations": ["-15.3875, 28.3228", "-15.4214, 28.2873"],
                "apps": ["WhatsApp v2.24.1", "Telegram v10.3", "Instagram v328"],
                "cloud": ["Drive: case_notes.pdf", "Drive: backup_0211.zip"],
                "deleted": ["Recovered msg #1", "Recovered msg #2", "Thumbnail cache"],
            }
            base = 7
            for category, items in samples.items():
                for _, item in enumerate(items):
                    ts = _utcnow() - timedelta(days=random.randint(0, 6),
                                              hours=random.randint(0, 23))
                    s.add(Artifact(case_id=demo.id, category=category, content=item,
                                   sender="Contact", recipient="DEVICE_OWNER",
                                   source=f"/data/{category}/file.db", timestamp=ts))
            s.add(AuditEntry(case_id=demo.id, user="analyst", action="demo_seeded",
                             details="synthetic data for development"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)