import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import proposal_searches as searches, source_cache, router_recovery
from app.db import Base, Project, Clip, Job, HighlightProposal, ProposalSearch
from app.schemas import ModelSelection


@pytest.fixture
def data(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(searches, "Session", factory)
    monkeypatch.setattr(searches, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(searches, "prepare", lambda *args: (tmp_path, None, 600))
    monkeypatch.setattr(searches, "wake", lambda: None)
    monkeypatch.setattr(router_recovery, "wake", lambda: None)
    from app import queue_runtime

    monkeypatch.setattr(queue_runtime, "Session", factory)
    (tmp_path / "metadata.json").write_text('{"title":"Podcast","duration":600}')
    words = [{"start": i, "end": i + 0.8, "text": "Usaha bisnis."} for i in range(600)]
    (tmp_path / "transcript.json").write_text(json.dumps({"words": words}))
    with factory() as s:
        project = Project(
            url="https://www.youtube.com/watch?v=niXAuUhK-tw",
            ai_combo="All-Combos",
            workflow="review",
            duration=600,
        )
        s.add(project)
        s.commit()
        pid = project.id
    yield factory, pid, tmp_path


def body(**kwargs):
    return searches.SearchInput(request_id=uuid4(), ai_combo="All-Combos", **kwargs)


def test_search_submission_is_idempotent_and_preserves_input(data):
    factory, pid, _ = data
    with factory() as s:
        p = s.get(Project, pid)
        request = body(additional_prompt="Cari bisnis", highlight_count=5)
        a = searches.enqueue_search(s, p, request)
        s.commit()
        b = searches.enqueue_search(s, p, request)
        assert a.id == b.id and len(list(s.scalars(select(Job)))) == 1
        assert a.count == 5 and a.prompt == "Cari bisnis"


def test_search_reuses_transcript_and_appends_without_replacing(data, monkeypatch):
    factory, pid, folder = data
    from app import transcription

    monkeypatch.setattr(
        transcription,
        "transcribe",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Transcription repeated")),
    )
    calls = []
    result = {
        "clips": [
            {
                "title": "Bisnis",
                "summary": "Memulai bisnis",
                "reason": "Pesan utuh",
                "start": 10,
                "end": 45,
            }
        ]
    }
    monkeypatch.setattr(
        searches,
        "generate",
        lambda *a, **kw: (calls.append(a), SimpleNamespace(text=json.dumps(result)))[1],
    )
    with factory() as s:
        a = searches.enqueue_search(s, s.get(Project, pid), body())
        s.commit()
        jid = a.job_id
    searches.run_search(jid, pid, "All-Combos", 1, "", lambda: None, lambda **kw: None)
    searches.run_search(jid, pid, "All-Combos", 1, "", lambda: None, lambda **kw: None)
    with factory() as s:
        original = s.scalar(select(HighlightProposal))
        assert len(list(s.scalars(select(HighlightProposal)))) == 1 and len(calls) == 1
        s.get(Job, jid).status = "succeeded"
        s.commit()
        result["clips"][0].update(start=100, end=140, title="Kegagalan")
        b = searches.enqueue_search(s, s.get(Project, pid), body())
        s.commit()
        next_jid = b.job_id
    searches.run_search(next_jid, pid, "All-Combos", 1, "", lambda: None, lambda **kw: None)
    with factory() as s:
        rows = list(s.scalars(select(HighlightProposal)))
        assert len(rows) == 2 and rows[0].id == original.id
        assert s.get(ProposalSearch, b.id).completed


def test_exclusions_cover_current_video_ranges_and_pending_proposals(data):
    factory, pid, _ = data
    with factory() as s:
        s.add(
            HighlightProposal(
                project_id=pid,
                title="Pending",
                start=30,
                end=90,
                original_start=30,
                original_end=90,
            )
        )
        s.add(
            Clip(
                project_id=pid,
                title="Video",
                plan={"segments": [{"source_in": 300, "duration": 60}]},
            )
        )
        s.commit()
        r = searches.enqueue_search(s, s.get(Project, pid), body())
        s.commit()
        assert r.exclusions == [[30, 90], [300, 360]]


def test_empty_results_are_reported_without_creating_fake_clips(data, monkeypatch):
    factory, pid, _ = data
    monkeypatch.setattr(
        searches,
        "generate",
        lambda *a, **kw: SimpleNamespace(text='{"clips":[],"unmet_requests":["Tidak ditemukan"]}'),
    )
    with factory() as s:
        r = searches.enqueue_search(s, s.get(Project, pid), body())
        s.commit()
    result = searches.run_search(
        r.job_id, pid, "All-Combos", 1, "Tidak ada", lambda: None, lambda **kw: None
    )
    with factory() as s:
        assert not list(s.scalars(select(HighlightProposal)))
        assert s.get(ProposalSearch, r.id).completed and result["generated"] == 0


def test_source_registration_deduplicates_url_variants_and_retains_files(data, monkeypatch):
    factory, pid, folder = data
    monkeypatch.setattr(source_cache, "Session", factory)
    monkeypatch.setattr(source_cache, "STORAGE", folder)
    (folder / "source.mp4").write_bytes(b"existing-source")
    with factory() as s:
        a = s.get(Project, pid)
        r = source_cache.source_record(s, a)
        b = Project(url="https://youtu.be/niXAuUhK-tw")
        s.add(b)
        s.flush()
        second = source_cache.source_record(s, b)
        s.commit()
        assert r.id == second.id
    root = source_cache.shared_folder(pid, folder)
    assert (root / "source.mp4").read_bytes() == b"existing-source"
    assert (folder / "source.mp4").read_bytes() == b"existing-source"


def test_explicit_router_recovery_preserves_project_and_is_idempotent(data):
    factory, pid, _ = data
    with factory() as s:
        old = Job(
            project_id=pid,
            kind="analysis",
            status="waiting_quota",
            payload={"workflow": "review", "highlight_count": 3},
        )
        s.add(old)
        s.commit()
        jid = old.id
        one = router_recovery.resume(jid, ModelSelection(ai_combo="All-Combos"), s)
        two = router_recovery.resume(jid, ModelSelection(ai_combo="All-Combos"), s)
        assert one["id"] == two["id"] and one["project_id"] == pid
        assert s.get(Job, jid).status == "cancelled"


def test_compaction_keeps_all_words_and_batches_overlap():
    words = [{"start": i, "end": i + 0.7, "text": "w" + str(i)} for i in range(1000)]
    groups = searches.compact_groups(words)
    assert sum(len(x["text"].split()) for x in groups) == 1000
    parts = list(searches.batches(groups, 1500))
    assert len(parts) > 1 and parts[1][0]["start"] < parts[0][-1]["end"]


def test_context_limit_splits_with_bounded_retry_and_keeps_coverage(data, monkeypatch):
    factory, pid, _ = data
    from app.router_ai import ContextLimit

    calls = []

    def generate(combo, content, *args, **kwargs):
        calls.append(content)
        # First attempt exceeds the downstream model context. Child requests succeed.
        if len(calls) == 1:
            raise ContextLimit("context")
        return SimpleNamespace(text='{"clips":[]}')

    monkeypatch.setattr(searches, "generate", generate)
    with factory() as s:
        r = searches.enqueue_search(s, s.get(Project, pid), body())
        s.commit()
    searches.run_search(r.job_id, pid, "All-Combos", 1, "", lambda: None, lambda **kw: None)
    assert len(calls) == 3
    assert "Usaha bisnis." in calls[1] and "Usaha bisnis." in calls[2]


@pytest.mark.parametrize("new_status", ["queued", "running", "succeeded", "failed", "cancelled"])
def test_superseded_legacy_analysis_cannot_create_another_search(data, new_status):
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException

    factory, pid, _ = data
    with factory() as s:
        old = Job(
            project_id=pid,
            kind="analysis",
            status="failed",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            payload={"workflow": "review"},
        )
        latest = Job(
            project_id=pid,
            kind="analysis",
            status=new_status,
            payload={"workflow": "review", "provider": "9router"},
        )
        s.add_all([old, latest])
        s.commit()
        with pytest.raises(HTTPException) as error:
            router_recovery.resume(old.id, ModelSelection(ai_combo="All-Combos"), s)
        assert error.value.status_code == 409
        assert "digantikan" in error.value.detail
        assert len(list(s.scalars(select(Job)))) == 2
        assert not list(s.scalars(select(ProposalSearch)))
        assert s.get(Job, old.id).status == "failed"


def test_only_latest_legacy_attempt_can_be_recovered(data):
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException

    factory, pid, _ = data
    with factory() as s:
        old = Job(
            project_id=pid,
            kind="analysis",
            status="failed",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            payload={"workflow": "review"},
        )
        latest = Job(
            project_id=pid, kind="analysis", status="failed", payload={"workflow": "review"}
        )
        s.add_all([old, latest])
        s.commit()
        with pytest.raises(HTTPException):
            router_recovery.resume(old.id, ModelSelection(ai_combo="All-Combos"), s)
        result = router_recovery.resume(latest.id, ModelSelection(ai_combo="All-Combos"), s)
        again = router_recovery.resume(latest.id, ModelSelection(ai_combo="All-Combos"), s)
        assert result["id"] == again["id"]
        assert len(list(s.scalars(select(ProposalSearch)))) == 1
