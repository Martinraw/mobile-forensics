"""SQLite case database built with SQLAlchemy 2.x ORM."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, create_engine, inspect, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, Session, mapped_column,
                            relationship, sessionmaker)


def default_db_path() -> Path:
    return Path.home() / ".forensic_suite" / "forensic_suite.db"


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    examiner: Mapped[str] = mapped_column(String(255))
    authorization_ref: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")

    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="case", cascade="all, delete-orphan")
    extractions: Mapped[list["Extraction"]] = relationship(
        back_populates="case", cascade="all, delete-orphan")
    audit_entries: Mapped[list["AuditEntry"]] = relationship(
        back_populates="case", cascade="all, delete-orphan")
    tool_runs: Mapped[list["ToolRun"]] = relationship(
        back_populates="case", cascade="all, delete-orphan")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    category: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extraction_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    case: Mapped["Case"] = relationship(back_populates="artifacts")


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    device: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    files: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    out_dir: Mapped[str] = mapped_column(Text, default="")
    info_json: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(Text, default="")

    case: Mapped["Case"] = relationship(back_populates="extractions")


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    time_utc: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    user: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255))
    details: Mapped[str] = mapped_column(Text, default="")

    case: Mapped["Case"] = relationship(back_populates="audit_entries")


class DeviceProfile(Base):
    __tablename__ = "device_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(255))
    os_version: Mapped[str] = mapped_column(String(64))
    imei: Mapped[str] = mapped_column(String(64))
    serial: Mapped[str] = mapped_column(String(128))
    connection: Mapped[str] = mapped_column(String(32), default="USB")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ToolRun(Base):
    __tablename__ = "tool_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    tool: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(255))
    command: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="ok")
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    output_json: Mapped[str] = mapped_column(Text, default="")

    case: Mapped["Case"] = relationship(back_populates="tool_runs")


class EvidenceFile(Base):
    """One file found inside an extraction (the Files section)."""

    __tablename__ = "evidence_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    extraction_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    folder: Mapped[str] = mapped_column(Text, default="", index=True)   # parent, relative
    rel_path: Mapped[str] = mapped_column(Text, default="")
    device_path: Mapped[str] = mapped_column(Text, default="")
    abs_path: Mapped[str] = mapped_column(Text, default="")
    ext: Mapped[str] = mapped_column(String(32), default="", index=True)
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    mime: Mapped[str] = mapped_column(String(128), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    md5: Mapped[str] = mapped_column(String(32), default="", index=True)
    created: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accessed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    key_evidence: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    tags: Mapped[str] = mapped_column(String(512), default="")          # comma separated
    note: Mapped[str] = mapped_column(Text, default="")
    hashset_match: Mapped[str] = mapped_column(String(255), default="")


class HashSet(Base):
    """A list of known (ignore) or notable (alert) file hashes."""

    __tablename__ = "hash_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default="notable")   # known | notable
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    entries: Mapped[int] = mapped_column(Integer, default=0)


class HashSetEntry(Base):
    __tablename__ = "hash_set_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("hash_sets.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), index=True)         # md5 or sha256, lower case


# Columns added after the first release: (table, column, SQL type + default).
_MIGRATIONS = [
    ("artifacts", "extraction_id", "INTEGER"),
    ("extractions", "out_dir", "TEXT DEFAULT ''"),
    ("extractions", "info_json", "TEXT DEFAULT '{}'"),
    ("extractions", "note", "TEXT DEFAULT ''"),
]


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = default_db_path()
        url = str(path)
        if "://" not in url:
            url = f"sqlite:///{url}"
        self.url = url
        self.engine = create_engine(url, connect_args={"check_same_thread": False})
        self._factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        parent = Path(self.url.replace("sqlite:///", "")).parent
        if str(parent) not in (".", ""):
            Path(parent).mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after the first release to an existing database."""
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        with self.engine.begin() as conn:
            for table, column, ddl in _MIGRATIONS:
                if table not in existing:
                    continue
                have = {c["name"] for c in inspector.get_columns(table)}
                if column not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()