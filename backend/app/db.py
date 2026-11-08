from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    Boolean,
    create_engine,
    String,
    Float,
    Integer,
    JSON,
    DateTime,
    ForeignKey,
    Table,
    Column,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    relationship,
    Session as ORMSession,
)
from sqlalchemy import event
from .config import settings


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


project_instansi = Table(
    "project_instansi",
    Base.metadata,
    Column(
        "project_id", String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "instansi_id",
        String(36),
        ForeignKey("instansi.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)
instasi_to_video_clips = Table(
    "instasi_to_video_clips",
    Base.metadata,
    Column(
        "video_clip_id",
        String(36),
        ForeignKey("video_clip.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "instansi_id",
        String(36),
        ForeignKey("instansi.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)
proposal_instansi = Table(
    "proposal_instansi",
    Base.metadata,
    Column(
        "proposal_id",
        String(36),
        ForeignKey("highlight_proposals.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "instansi_id",
        String(36),
        ForeignKey("instansi.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)
clip_instansi = Table(
    "clip_instansi",
    Base.metadata,
    Column("clip_id", String(36), ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "instansi_id",
        String(36),
        ForeignKey("instansi.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)


class Instansi(Base):
    __tablename__ = "instansi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(300), unique=True)


class MediaSource(Base):
    __tablename__ = "media_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    youtube_id: Mapped[str] = mapped_column(String(11), unique=True)
    url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProposalSearch(Base):
    __tablename__ = "proposal_searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    combo: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(String(4000), default="")
    count: Mapped[int] = mapped_column(Integer, default=1)
    avoid_used: Mapped[bool] = mapped_column(Boolean, default=True)
    exclusions: Mapped[list] = mapped_column(JSON, default=list)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HighlightRequest(Base):
    __tablename__ = "highlight_requests"
    __table_args__ = (UniqueConstraint("project_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    search_id: Mapped[str | None] = mapped_column(
        ForeignKey("proposal_searches.id", ondelete="SET NULL"), nullable=True
    )
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("highlight_proposals.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    number: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(String(2000), default="")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("media_sources.id"), nullable=True, index=True
    )
    ai_combo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    workflow: Mapped[str] = mapped_column(String(16), default="legacy")
    __tablename__ = "projects"
    request_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    include_global: Mapped[bool] = mapped_column(Boolean, default=True)
    instansi_records: Mapped[list[Instansi]] = relationship(
        secondary=project_instansi, lazy="selectin", order_by=Instansi.name
    )

    @property
    def instansi_ids(self):
        return sorted(item.id for item in self.instansi_records)

    mix_hashtags: Mapped[list] = mapped_column(JSON, default=list)
    visual_mode: Mapped[str] = mapped_column(String(16), default="podcast")
    subtitle_mode: Mapped[str] = mapped_column(String(16), default="sentence")
    subtitle_animation: Mapped[str] = mapped_column(String(16), default="none")
    aspect_ratio: Mapped[str] = mapped_column(String(8), default="9:16")
    highlight_count: Mapped[int] = mapped_column(Integer, default=3)
    additional_prompt: Mapped[str] = mapped_column(String(4000), default="")
    analysis_report: Mapped[dict] = mapped_column(JSON, default=dict)
    url: Mapped[str] = mapped_column(String(2048))
    gemini_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="Video YouTube")
    duration: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Clip(Base):
    ready: Mapped[bool] = mapped_column(Boolean, default=True)
    aspect_ratio: Mapped[str] = mapped_column(String(8), default="9:16")
    processing_config: Mapped[dict] = mapped_column(JSON, default=dict)
    instansi_records: Mapped[list[Instansi]] = relationship(
        secondary=clip_instansi, lazy="selectin"
    )

    @property
    def instansi_ids(self):
        return sorted(x.id for x in self.instansi_records)

    __tablename__ = "clips"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(2000), default="Clip manual")
    legacy_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fulfills_prompt: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    plan: Mapped[dict] = mapped_column(JSON)


class HighlightProposal(Base):
    search_id: Mapped[str | None] = mapped_column(
        ForeignKey("proposal_searches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    __tablename__ = "highlight_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(2000), default="")
    reason: Mapped[str] = mapped_column(String(2000), default="")
    original_start: Mapped[int] = mapped_column(Integer)
    original_end: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    fulfills_prompt: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    clip_id: Mapped[str | None] = mapped_column(
        ForeignKey("clips.id", ondelete="SET NULL"), nullable=True
    )
    instansi_records: Mapped[list[Instansi]] = relationship(
        secondary=proposal_instansi, lazy="selectin"
    )

    @property
    def instansi_ids(self):
        return sorted(x.id for x in self.instansi_records)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    library_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_clip.id", ondelete="SET NULL"), nullable=True, index=True
    )
    queue_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    wait_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    connection_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=True
    )
    clip_id: Mapped[str | None] = mapped_column(ForeignKey("clips.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="Menunggu antrean")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    telemetry: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


video_clip_hashtags = Table(
    "video_clip_hashtags",
    Base.metadata,
    Column(
        "video_clip_id",
        String(36),
        ForeignKey("video_clip.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "hashtag_id",
        String(36),
        ForeignKey("hashtags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class Hashtag(Base):
    __tablename__ = "hashtags"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name_tag: Mapped[str] = mapped_column(String(50), unique=True)


class VideoClip(Base):
    __tablename__ = "video_clip"
    __table_args__ = (
        CheckConstraint("scope IN ('global','instansi')", name="ck_video_clip_scope"),
    )
    scope: Mapped[str] = mapped_column(String(16), default="global")
    instansi_records: Mapped[list[Instansi]] = relationship(
        secondary=instasi_to_video_clips, lazy="selectin", order_by=Instansi.name
    )

    @property
    def instansi_ids(self):
        return sorted(item.id for item in self.instansi_records)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(200))
    url_path: Mapped[str] = mapped_column(String(500), default="")
    tag_records: Mapped[list[Hashtag]] = relationship(
        secondary=video_clip_hashtags, lazy="selectin", order_by=Hashtag.name_tag
    )

    @property
    def hashtags(self):
        return [tag.name_tag for tag in self.tag_records]

    explain: Mapped[str] = mapped_column(String(4000), default="")
    scenes: Mapped[list] = mapped_column(JSON, default=list)
    duration: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@event.listens_for(ORMSession, "before_flush")
def track_project_changes(s, flush_context, instances):
    changed = set(s.new) | set(s.dirty) | set(s.deleted)
    project_ids = set()
    for item in changed:
        if (
            item not in s.new
            and item not in s.deleted
            and not s.is_modified(item, include_collections=True)
        ):
            continue
        if isinstance(item, Project) and item not in s.deleted:
            item.updated_at = now()
        elif isinstance(item, (Clip, HighlightProposal)):
            project_ids.add(item.project_id)
    for pid in project_ids:
        project = s.get(Project, pid)
        if project is not None and project not in s.deleted:
            project.updated_at = now()


engine = (
    create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=3,
        pool_pre_ping=True,
        pool_recycle=120,
        connect_args={
            "connect_timeout": 3,
            "keepalives": 1,
            "keepalives_idle": 5,
            "keepalives_interval": 2,
            "keepalives_count": 3,
            "tcp_user_timeout": 10000,
            "options": "-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000",
        },
    )
    if settings.database_url
    else None
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def session():
    if engine is None:
        from fastapi import HTTPException

        raise HTTPException(
            503, "Database belum dikonfigurasi. Isi DATABASE_URL di .env lalu jalankan migrasi."
        )
    with Session() as s:
        yield s
