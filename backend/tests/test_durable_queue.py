from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from app import queue_runtime as queue, main, tasks
from app.db import Base, Project, Job, VideoClip
from app.schemas import ProjectInput


@pytest.fixture
def db(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    for module in (queue, tasks):
        monkeypatch.setattr(module, "Session", factory)
    monkeypatch.setattr(queue, "engine", engine)
    monkeypatch.setattr(queue, "STORAGE", tmp_path)
    monkeypatch.setattr(main, "wake", lambda: None)
    monkeypatch.setattr(main, "validate_model", lambda _: None)
    yield factory
    engine.dispose()


def seed(factory, n=3):
    with factory() as s:
        jobs = []
        for i in range(n):
            p = Project(url="test")
            s.add(p)
            s.flush()
            j = Job(
                project_id=p.id,
                kind="analysis",
                queue_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
            )
            s.add(j)
            s.flush()
            jobs.append(j.id)
        s.commit()
        return jobs


def test_fifo_wait_skip_and_reentry(db):
    ids = seed(db)
    with db() as s:
        a = s.get(Job, ids[0])
        a.status = "waiting_quota"
        a.next_attempt_at = None
        s.commit()
    with queue.heavy_guard() as g:
        assert queue.claim(g) == ids[1]
        with queue.heavy_guard() as other:
            assert other is None
        with db() as s:
            s.get(Job, ids[1]).status = "succeeded"
            s.commit()
    with db() as s:
        s.get(Job, ids[0]).next_attempt_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        s.commit()
    with queue.heavy_guard() as g:
        assert queue.claim(g) == ids[0]


def test_recovery_preserves_checkpoint_and_cancelled_not_restarted(db):
    ids = seed(db, 2)
    with db() as s:
        a = s.get(Job, ids[0])
        a.status = "running"
        a.owner_token = "old"
        a.checkpoint = {"analysis": {"ok": True}}
        b = s.get(Job, ids[1])
        b.status = "cancelling"
        s.commit()
    with queue.heavy_guard() as g:
        assert queue.claim(g) == ids[0]
    with db() as s:
        assert s.get(Job, ids[0]).checkpoint == {"analysis": {"ok": True}}
        assert s.get(Job, ids[1]).status == "cancelled"


def test_atomic_create_idempotency_and_snapshot(db):
    rid = uuid4()
    body = ProjectInput(
        url="https://youtu.be/dQw4w9WgXcQ",
        gemini_model="gemini-test",
        enqueue_analysis=True,
        request_id=rid,
    )
    with db() as s:
        a = main.create_project(body, s)
        b = main.create_project(body, s)
        assert a["id"] == b["id"]
        assert len(list(s.scalars(select(Project)))) == 1
        jobs = list(s.scalars(select(Job)))
        assert len(jobs) == 1
        assert jobs[0].payload["gemini_model"] == "gemini-test"
        assert "request_hash" not in a
        with pytest.raises(HTTPException) as exc:
            main.create_project(body.model_copy(update={"highlight_count": 5}), s)
        assert exc.value.status_code == 409


def test_failure_does_not_leave_half_project(db, monkeypatch):
    monkeypatch.setattr(
        main, "analysis_payload", lambda *_: (_ for _ in ()).throw(RuntimeError("snapshot failed"))
    )
    with db() as s:
        with pytest.raises(RuntimeError):
            main.create_project(
                ProjectInput(
                    url="https://youtu.be/dQw4w9WgXcQ",
                    gemini_model="gemini-test",
                    enqueue_analysis=True,
                ),
                s,
            )
        s.rollback()
        assert list(s.scalars(select(Project))) == []


def test_cancel_keeps_slot_until_worker_stops_and_retry_appends(db):
    ids = seed(db, 2)
    with db() as s:
        j = s.get(Job, ids[0])
        j.status = "running"
        j.checkpoint = {"saved": 1}
        s.commit()
        assert main.cancel(j.id, s)["status"] == "cancelling"
        with pytest.raises(HTTPException):
            main.delete_project(j.project_id, s)
        j.status = "cancelled"
        s.commit()
        new = main.retry(j.id, s)
        assert s.get(Job, new["id"]).checkpoint == {"saved": 1}
        assert new["queue_position"] == 2


def test_library_has_durable_queue_item(db):
    with db() as s:
        v = VideoClip(title="Test")
        s.add(v)
        s.flush()
        first = queue.add_library(s, v.id)
        s.flush()
        second = queue.add_library(s, v.id)
        s.commit()
        assert first.id == second.id and first.project_id is None
        assert first.kind == "library"


def test_worker_persists_provider_wait_and_preserves_snapshot(db, monkeypatch, tmp_path):
    from app.router_ai import ProviderWait

    ids = seed(db, 1)
    monkeypatch.setattr(tasks, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(tasks.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**10))
    monkeypatch.setattr(
        tasks,
        "analyze",
        lambda *args: (_ for _ in ()).throw(ProviderWait("Batas sementara", "waiting_quota")),
    )
    tasks.execute.run()
    with db() as s:
        j = s.get(Job, ids[0])
        assert (
            j.status == "waiting_quota" and j.next_attempt_at is not None and j.owner_token is None
        )


def test_export_and_media_can_queue_behind_same_project_analysis(db):
    ids = seed(db, 1)
    with db() as s:
        analysis = s.get(Job, ids[0])
        analysis.status = "waiting_quota"
        s.commit()
        export = main.enqueue(s, analysis.project_id, "export", payload={"revision": 1})
        duplicate = main.enqueue(s, analysis.project_id, "export", payload={"revision": 1})
        assert export["id"] == duplicate["id"]
        media = main.enqueue(s, analysis.project_id, "editor_media")
        assert media["id"] != export["id"]
        with pytest.raises(HTTPException):
            main.enqueue(s, analysis.project_id, "analysis")


def test_library_low_disk_failure_does_not_loop_forever(db, monkeypatch):
    with db() as s:
        v = VideoClip(title="No disk")
        s.add(v)
        s.flush()
        aid = v.id
        queue.add_library(s, aid)
        s.commit()
    monkeypatch.setattr(tasks.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    tasks.execute.run()
    with db() as s:
        assert s.get(VideoClip, aid).status == "failed"
        assert len(list(s.scalars(select(Job)))) == 1
    with queue.heavy_guard() as g:
        assert queue.claim(g) is None


def test_database_outage_waits_without_terminal_failure(db, monkeypatch):
    from sqlalchemy.exc import OperationalError

    jid = seed(db, 1)[0]
    with db() as s:
        s.get(Job, jid).status = "running"
        s.commit()
    monkeypatch.setattr(tasks.shutil, "disk_usage", lambda _: SimpleNamespace(free=10 * 1024**3))
    monkeypatch.setattr(tasks, "project_dir", lambda _: __import__("pathlib").Path("/tmp"))
    monkeypatch.setattr(
        tasks,
        "analyze",
        lambda *_: (_ for _ in ()).throw(
            OperationalError("select", {}, Exception("temporary connection issue"))
        ),
    )
    tasks.process_job(jid)
    with db() as s:
        job = s.get(Job, jid)
        assert job.status == "waiting_service" and job.telemetry["wait_kind"] == "database"
        assert job.next_attempt_at is not None and job.error is None


def test_router_configuration_change_wakes_waiting_work(db, monkeypatch):
    from app.router_ai import configuration, ENV_PATH

    original = configuration().identity
    monkeypatch.setattr(queue, "_config_revision", original)
    jid = seed(db, 1)[0]
    with db() as s:
        job = s.get(Job, jid)
        job.status = "waiting_service"
        job.stage = "Menunggu konfigurasi 9Router"
        job.next_attempt_at = None
        s.commit()
    calls = []
    monkeypatch.setattr(queue, "wake", lambda: calls.append(True))
    ENV_PATH.write_text(
        "9router_base_url=http://127.0.0.1:20128/v1\n9router_key=replaced-test-only\n"
    )
    queue.dispatch_once()
    with db() as s:
        assert s.get(Job, jid).next_attempt_at is not None
