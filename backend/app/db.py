from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, create_engine, String, Float, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass
class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    aspect_ratio: Mapped[str] = mapped_column(String(8),default='9:16')
    highlight_count: Mapped[int] = mapped_column(Integer,default=3)
    additional_prompt: Mapped[str] = mapped_column(String(4000),default='')
    analysis_report: Mapped[dict] = mapped_column(JSON,default=dict)
    url: Mapped[str] = mapped_column(String(2048))
    gemini_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default='Video YouTube')
    duration: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default='new')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Clip(Base):
    __tablename__ = 'clips'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(2000), default='Clip manual')
    legacy_plan: Mapped[dict | None] = mapped_column(JSON,nullable=True)
    fulfills_prompt: Mapped[bool] = mapped_column(Boolean,default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    plan: Mapped[dict] = mapped_column(JSON)
class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    clip_id: Mapped[str | None] = mapped_column(ForeignKey('clips.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default='queued')
    stage: Mapped[str] = mapped_column(String(80), default='Menunggu antrean')
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

engine = create_engine(settings.database_url, poolclass=NullPool, connect_args={'connect_timeout': 3, 'keepalives': 1, 'keepalives_idle': 5, 'keepalives_interval': 2, 'keepalives_count': 3, 'tcp_user_timeout': 10000, 'options': '-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000'}) if settings.database_url else None
Session = sessionmaker(bind=engine, expire_on_commit=False)
def session():
    if engine is None:
        from fastapi import HTTPException
        raise HTTPException(503, 'Database belum dikonfigurasi. Isi DATABASE_URL di .env lalu jalankan migrasi.')
    with Session() as s: yield s
