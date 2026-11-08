"""Durable, single-slot heavy-work queue. Celery messages are wakeups only."""

from contextlib import contextmanager
from datetime import timedelta
from threading import Event, Thread, Lock
from uuid import uuid4
import fcntl
import os
from sqlalchemy import select, text, or_, update as sql_update
from sqlalchemy.exc import SQLAlchemyError
from .db import Session, Job, VideoClip, engine, now
from .config import STORAGE
from .media import Cancelled

PENDING = ("queued", "running", "cancelling", "waiting_quota", "waiting_service", "waiting_network")
WAITING = ("waiting_quota", "waiting_service", "waiting_network")
LOCK_ID = 861470263


def eligible():
    return or_(
        Job.status == "queued",
        (Job.status.in_(WAITING))
        & (Job.next_attempt_at.is_not(None))
        & (Job.next_attempt_at <= now()),
    )


def position(s, job):
    if job.status != "queued":
        return None
    rows = list(s.scalars(select(Job.id).where(eligible()).order_by(Job.queue_at, Job.id)))
    return rows.index(job.id) + 1 if job.id in rows else None


def public_job(s, j):
    keys = (
        "id",
        "project_id",
        "clip_id",
        "kind",
        "status",
        "stage",
        "progress",
        "error",
        "payload",
        "result",
        "created_at",
        "queue_at",
        "next_attempt_at",
        "wait_reason",
        "connection_label",
        "heartbeat_at",
        "telemetry",
    )
    return {**{k: getattr(j, k) for k in keys}, "queue_position": position(s, j)}


def wake():
    try:
        from .tasks import execute

        execute.apply_async(args=[], retry=False)
    except Exception:
        # The database remains authoritative when Redis is temporarily down.
        pass


def add_library(s, aid):
    s.execute(select(VideoClip).where(VideoClip.id == aid).with_for_update()).scalar_one()
    existing = s.scalar(select(Job).where(Job.library_id == aid, Job.status.in_(PENDING)))
    if existing:
        return existing
    j = Job(kind="library", library_id=aid, payload={"asset_id": aid})
    s.add(j)
    return j


class Guard:
    def __init__(self, conn):
        self.conn = conn
        self.stop = Event()
        self.lost = Event()
        self.mutex = Lock()
        self.job_id = None
        self.owner = str(uuid4())
        self.thread = Thread(target=self.pulse, daemon=True)
        self.thread.start()

    def pulse(self):
        while not self.stop.wait(3):
            try:
                if self.conn is not None:
                    with self.mutex:
                        self.conn.execute(text("SELECT 1"))
            except Exception:
                self.lost.set()
                return
            if self.job_id:
                try:
                    with Session() as s:
                        s.execute(
                            sql_update(Job)
                            .where(Job.id == self.job_id, Job.owner_token == self.owner)
                            .values(heartbeat_at=now())
                        )
                        s.commit()
                except SQLAlchemyError:
                    from .job_diagnostics import event

                    event("heartbeat_write_interrupted", job_id=self.job_id)

    def check(self):
        if self.lost.is_set():
            raise Cancelled()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=20)


@contextmanager
def heavy_guard():
    # flock also protects surviving FFmpeg descendants if a worker dies while
    # PostgreSQL releases its advisory lock. media.run passes this FD to children.
    STORAGE.mkdir(parents=True, exist_ok=True)
    f = (STORAGE / "heavy-work.lock").open("a+")
    conn = None
    guard = None
    locked = False
    try:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
            return
        if engine is not None and engine.dialect.name == "postgresql":
            conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            if not conn.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}):
                yield None
                return
            locked = True
        os.environ["VC_HEAVY_LOCK_FD"] = str(f.fileno())
        guard = Guard(conn)
        yield guard
    finally:
        os.environ.pop("VC_HEAVY_LOCK_FD", None)
        if guard:
            guard.close()
        if conn is not None:
            try:
                if locked:
                    conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
            except SQLAlchemyError:
                conn.invalidate()
            finally:
                conn.close()
        # Closing our descriptor does not release locks inherited by live children.
        f.close()


def claim(guard):
    """Caller owns both global locks; an old running owner is now provably gone."""
    with Session() as s:
        for j in s.scalars(
            select(Job).where(Job.status.in_(("running", "cancelling"))).with_for_update()
        ):
            if j.status == "cancelling":
                j.status = "cancelled"
                j.stage = "Dibatalkan"
                if j.library_id:
                    v = s.get(VideoClip, j.library_id)
                    if v:
                        v.status = "failed"
                        v.error = "Persiapan dibatalkan."
            else:
                j.status = "queued"
                j.stage = "Melanjutkan setelah terputus"
            j.owner_token = None
            j.heartbeat_at = None
        # Upgrade queued library work from the old direct Celery task format.
        for v in s.scalars(select(VideoClip).where(VideoClip.status.in_(("queued", "processing")))):
            add_library(s, v.id)
        s.flush()
        j = s.scalar(
            select(Job)
            .where(eligible())
            .order_by(Job.queue_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if j is None:
            s.commit()
            return None
        j.telemetry = {**(j.telemetry or {}), "wait_kind": None}
        j.status = "running"
        j.stage = "Menyiapkan"
        j.owner_token = guard.owner
        j.heartbeat_at = now()
        j.error = None
        j.wait_reason = None
        j.next_attempt_at = None
        guard.job_id = j.id
        s.commit()
        return j.id


def checkpoint(jid, key, value):
    with Session() as s:
        j = s.scalar(select(Job).where(Job.id == jid).with_for_update())
        if not j or j.status in ("cancelled", "cancelling"):
            raise Cancelled()
        j.checkpoint = {**j.checkpoint, key: value}
        s.commit()


def read_checkpoint(jid, key):
    with Session() as s:
        j = s.get(Job, jid)
        return j.checkpoint.get(key) if j and isinstance(j.checkpoint, dict) else None


_config_revision = None


def dispatch_once():
    global _config_revision
    from .router_ai import configuration, ConfigError

    try:
        revision = configuration().identity
        if revision != _config_revision:
            with Session() as config_session:
                for waiting in config_session.scalars(
                    select(Job)
                    .where(Job.status == "waiting_service", Job.stage.like("Menunggu konfigurasi%"))
                    .with_for_update()
                ):
                    waiting.next_attempt_at = now()
                config_session.commit()
            _config_revision = revision
    except ConfigError:
        _config_revision = None
    with Session() as s:
        # Only the worker owning the locks can recover stale running work.
        healthy = s.scalar(
            select(Job.id).where(
                Job.status.in_(("running", "cancelling")),
                Job.heartbeat_at > now() - timedelta(seconds=20),
            )
        )
        pending = s.scalar(
            select(Job.id).where(Job.status.in_(("running", "cancelling")) | eligible())
        )
        legacy = s.scalar(
            select(VideoClip.id).where(VideoClip.status.in_(("queued", "processing")))
        )
    if not healthy and (pending or legacy):
        wake()


if __name__ == "__main__":
    import time

    while True:
        try:
            dispatch_once()
        except Exception:
            pass
        time.sleep(3)
