"""Export admission tests never enqueue Celery or render user media."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import sessionmaker
from app import main
from app.config import settings
from app.db import Base, Project, Clip, Job
from app.queue_runtime import PENDING


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "admission.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(main, "live_job_payload", lambda s, payload: payload)
    monkeypatch.setattr(main, "wake", lambda: None)
    with factory() as s:
        for pid in ("a", "b"):
            s.add(Project(id=pid, url="https://example.com/" + pid))
            s.flush()
            s.add(Clip(id=pid, project_id=pid, title=pid, plan={}))
        s.commit()
    yield factory
    engine.dispose()


@pytest.mark.parametrize("status", PENDING)
def test_all_pending_states_block_other_exports(db, status):
    with db() as s:
        original = main.add_job(s, "a", "export", "a", {"resolution": 1080})
        original.status = status
        s.commit()
        assert main.add_job(s, "a", "export", "a", {"resolution": 1080}).id == original.id
        with pytest.raises(HTTPException) as caught:
            main.add_job(s, "b", "export", "b", {"resolution": 1080})
        assert caught.value.status_code == 409
        s.rollback()


@pytest.mark.parametrize(
    "payload,clip,pid",
    [
        ({"resolution": 720}, "a", "a"),
        ({"resolution": 1080, "revision": 2}, "a", "a"),
        ({"resolution": 1080}, "b", "b"),
    ],
)
def test_different_snapshot_or_clip_blocked(db, payload, clip, pid):
    with db() as s:
        main.enqueue(s, "a", "export", "a", {"resolution": 1080})
        with pytest.raises(HTTPException):
            main.enqueue(s, pid, "export", clip, payload)


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_terminal_exports_release_admission(db, status):
    with db() as s:
        old = main.add_job(s, "a", "export", "a", {})
        old.status = status
        s.commit()
        assert main.enqueue(s, "b", "export", "b", {})["status"] == "queued"


def test_retry_uses_same_guard_and_non_export_does_not_block(db):
    with db() as s:
        main.enqueue(s, "a", "preview", "a", {})
        failed = Job(
            project_id="a", clip_id="a", kind="export", status="failed", payload={"project_id": "a"}
        )
        s.add(failed)
        s.commit()
        main.enqueue(s, "b", "export", "b", {})
        with pytest.raises(HTTPException) as caught:
            main.retry(failed.id, s)
        assert caught.value.status_code == 409


@pytest.mark.skipif(
    os.environ.get("TEST_EXPORT_POSTGRES") != "1", reason="Opt-in isolated PostgreSQL schema"
)
@pytest.mark.parametrize("retry", [False, True])
def test_concurrent_postgres_admission(monkeypatch, retry):
    schema = "qa_export_" + uuid4().hex
    admin = create_engine(settings.database_url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine)
        monkeypatch.setattr(main, "live_job_payload", lambda s, payload: payload)
        monkeypatch.setattr(main, "wake", lambda: None)
        with factory() as s:
            for pid in ("a", "b"):
                s.add(Project(id=pid, url="https://example.com/" + pid))
                s.flush()
                s.add(Clip(id=pid, project_id=pid, title=pid, plan={}))
            s.flush()
            old = Job(
                id="old",
                project_id="b",
                clip_id="b",
                kind="export",
                status="failed",
                payload={"project_id": "b"},
            )
            s.add(old)
            s.commit()
        barrier = Barrier(2)

        def submit(pid):
            with factory() as s:
                barrier.wait(timeout=10)
                try:
                    if retry and pid == "b":
                        result = main.retry("old", s)
                    else:
                        result = main.enqueue(s, pid, "export", pid, {})
                    return result["id"]
                except HTTPException as exc:
                    s.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ["a", "b"]))
        assert results.count(409) == 1
        with factory() as s:
            assert (
                s.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.kind == "export", Job.status.in_(PENDING))
                )
                == 1
            )
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
