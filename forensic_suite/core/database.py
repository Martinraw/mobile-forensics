"""SQLite case database built with SQLAlchemy 2.x ORM."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
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
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

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


class Database:
    """Owns the engine and exposes a session context manager.

    ``check_same_thread=False`` is required because Qt workers touch the DB
    from worker threads.
    """

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