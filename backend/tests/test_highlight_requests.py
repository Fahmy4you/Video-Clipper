import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from test_proposal_searches import data, body
from app import proposal_searches as searches, highlight_requests as requests
from app import search_selection as selection, source_info
from app.db import Project, Job, HighlightProposal, HighlightRequest, ProposalSearch


def v2(**kwargs):
    return body(policy_version=2, **kwargs)


def execute(factory, pid, request):
    with factory() as s:
        record = searches.enqueue_search(s, s.get(Project, pid), request)
        s.commit()
        jid = record.job_id
    return jid, lambda: searches.run_search(
        jid,
        pid,
        request.ai_combo,
        request.highlight_count,
        request.additional_prompt,
        lambda: None,
        lambda **kw: None,
    )


@pytest.mark.parametrize(
    "prompt,timing,avoid",
    [
        ("", None, True),
        ("  ", None, True),
        ("Bisnis", None, False),
        ("", {"start_frame": 0, "end_frame": 300, "fix_time": True}, False),
    ],
)
def test_policy_is_derived_server_side(prompt, timing, avoid):
    assert v2(additional_prompt=prompt, time_range=timing).avoid_used == avoid


@pytest.mark.parametrize(
    "duration,ok",
    [(9.99, False), (10, True), (29, True), (18000, True), (18000.01, False), (0, False)],
)
def test_source_limits(duration, ok, monkeypatch):
    monkeypatch.setattr(source_info.settings, "source_min_duration_seconds", 10)
    if ok:
        assert source_info.validate_duration(duration) == duration
    else:
        with pytest.raises(HTTPException):
            source_info.validate_duration(duration)


def raw(a, b):
    return {
        "start": a,
        "end": b,
        "title": "Isi podcast",
        "summary": "Ringkasan",
        "reason": "Konteks utuh",
    }


def test_explicit_time_and_flexible_bounds():
    fixed = {"start_frame": 3000, "end_frame": 9000, "fix_time": True}
    assert selection.valid_candidate(raw(100, 300), 600, fixed, [])
    assert selection.valid_candidate(raw(99, 300), 600, fixed, []) is None
    flexible = {**fixed, "fix_time": False}
    assert selection.valid_candidate(raw(40, 360), 600, flexible, [])
    assert selection.valid_candidate(raw(39.96, 360), 600, flexible, []) is None
    assert selection.valid_candidate(raw(100, 300), 600, fixed, [[1000, 4000]]) is None
    assert selection.valid_candidate(raw(0, 10), 10, None, [])
    assert selection.valid_candidate(raw(0, 9), 10, None, []) is None


def test_missing_results_have_real_items_but_no_fake_proposals(data, monkeypatch):
    factory, pid, _ = data
    monkeypatch.setattr(
        searches,
        "generate",
        lambda *a, **kw: SimpleNamespace(
            text='{"clips":[],"unmet_requests":["Topik tidak ditemukan"]}'
        ),
    )
    jid, run = execute(factory, pid, v2(highlight_count=5))
    run()
    with factory() as s:
        items = list(s.scalars(select(HighlightRequest)))
        assert len(items) == 5 and all(x.status == "unfulfilled" for x in items)
        assert not list(s.scalars(select(HighlightProposal)))
        requests.backfill(s)
        s.flush()
        assert len(list(s.scalars(select(HighlightRequest)))) == 5


def test_selection_repair_uses_ids_and_preserves_partial_success(data, monkeypatch):
    factory, pid, _ = data
    monkeypatch.setattr(searches, "batches", lambda groups: iter([groups[:30], groups[30:]]))
    batches, selections = [], []

    def generate(combo, content, config, *args):
        schema = config["response_schema"]
        if schema is searches.Highlights:
            offset = len(batches) * 250
            batches.append(content)
            return SimpleNamespace(
                text=json.dumps(
                    {"clips": [raw(10 + offset + i * 50, 45 + offset + i * 50) for i in range(5)]}
                )
            )
        info = json.loads(content.split("\n")[-1])
        selections.append(info)
        ids = [x["candidate_id"] for x in info["candidates"]]
        if len(selections) == 1:
            return SimpleNamespace(text=json.dumps({"ids": ids[:1]}))
        with factory() as s:
            assert len(list(s.scalars(select(HighlightProposal)))) == 1
        return SimpleNamespace(text=json.dumps({"ids": ids[1:5]}))

    monkeypatch.setattr(searches, "generate", generate)
    jid, run = execute(factory, pid, v2(highlight_count=5))
    assert run()["generated"] == 5
    run()
    assert len(batches) == 2 and len(selections) == 2
    with factory() as s:
        assert len(list(s.scalars(select(HighlightProposal)))) == 5
        assert all(x.proposal_id for x in s.scalars(select(HighlightRequest)))


def test_retry_fills_same_item_and_does_not_delete_source(data, monkeypatch):
    factory, pid, folder = data
    monkeypatch.setattr(requests, "wake", lambda: None)
    monkeypatch.setattr(searches, "generate", lambda *a, **kw: SimpleNamespace(text='{"clips":[]}'))
    jid, run = execute(factory, pid, v2())
    run()
    with factory() as s:
        s.get(Job, jid).status = "succeeded"
        s.commit()
        item = s.scalar(select(HighlightRequest))
        itemid = item.id
        retry = requests.RetryInput(
            request_id=uuid4(), revision=item.revision, ai_combo="All-Combos"
        )
        one = requests.reanalyze(item.id, retry, s)
        two = requests.reanalyze(item.id, retry, s)
        assert one["id"] == two["id"]
        assert len(list(s.scalars(select(HighlightRequest)))) == 1
        s.get(Job, one["id"]).status = "failed"
        s.commit()
        item = s.get(HighlightRequest, itemid)
        requests.remove(itemid, item.revision, s)
        assert s.get(HighlightRequest, itemid).deleted
        assert (folder / "transcript.json").exists()
        assert s.get(Project, pid)


def test_failed_video_does_not_mark_analysis_failed(data):
    factory, pid, _ = data
    with factory() as s:
        p = HighlightProposal(
            project_id=pid, title="Usulan", start=0, end=900, original_start=0, original_end=900
        )
        s.add(p)
        s.flush()
        job = Job(project_id=pid, kind="build_highlight", status="failed")
        s.add(job)
        s.flush()
        p.job_id = job.id
        item = HighlightRequest(project_id=pid, number=1, proposal_id=p.id, status="fulfilled")
        s.add(item)
        s.commit()
        result = requests.item_view(s, item)
        assert result["status"] == "fulfilled" and result["proposal"]["status"] == "failed"


def test_fixed_range_overrides_general_duration_target(data, monkeypatch):
    factory, pid, _ = data
    monkeypatch.setattr(
        searches,
        "generate",
        lambda *a, **kw: SimpleNamespace(text=json.dumps({"clips": [raw(100, 300)]})),
    )
    jid, run = execute(
        factory, pid, v2(time_range={"start_frame": 3000, "end_frame": 9000, "fix_time": True})
    )
    assert run()["generated"] == 1
    with factory() as s:
        p = s.scalar(select(HighlightProposal))
        assert (p.start, p.end) == (3000, 9000)


def test_deleted_item_is_not_resurrected_by_late_completion(data, monkeypatch):
    factory, pid, _ = data
    monkeypatch.setattr(
        searches,
        "generate",
        lambda *a, **kw: SimpleNamespace(text=json.dumps({"clips": [raw(10, 45)]})),
    )
    jid, run = execute(factory, pid, v2())
    with factory() as s:
        item = s.scalar(select(HighlightRequest))
        item.deleted = True
        s.commit()
    run()
    with factory() as s:
        assert not list(s.scalars(select(HighlightProposal)))
        assert s.scalar(select(HighlightRequest)).deleted


def test_source_metadata_reads_existing_source_without_downloading(data, monkeypatch):
    factory, pid, _ = data
    monkeypatch.setattr(source_info, "Session", factory)
    source_info._cache.clear()
    import yt_dlp

    monkeypatch.setattr(
        yt_dlp,
        "YoutubeDL",
        lambda *a, **kw: pytest.fail("Cached source should not download or fetch metadata"),
    )
    result = source_info.inspect_source("https://youtu.be/niXAuUhK-tw")
    assert result["duration"] == 600 and result["min_duration"] == 10


def test_metadata_provider_never_downloads_video(monkeypatch):
    from app.db import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(source_info, "Session", sessionmaker(bind=engine))
    source_info._cache.clear()
    import yt_dlp

    seen = []

    class Fake:
        def __init__(self, options):
            assert options["skip_download"]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def extract_info(self, url, download):
            seen.append(download)
            return {"title": "Kripto", "duration": 10}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Fake)
    assert source_info.inspect_source("https://youtu.be/abcdefghijk")["duration"] == 10
    assert seen == [False]


@pytest.mark.parametrize(
    "timing", [None, {"start_frame": 300, "end_frame": 1350, "fix_time": False}]
)
def test_explicit_topic_does_not_return_nonmatching_candidate(data, monkeypatch, timing):
    factory, pid, _ = data
    monkeypatch.setattr(
        searches,
        "generate",
        lambda *a, **kw: SimpleNamespace(
            text=json.dumps({"clips": [{**raw(10, 45), "fulfills_prompt": False}]})
        ),
    )
    jid, run = execute(
        factory, pid, v2(additional_prompt="Cari topik yang tidak dibahas", time_range=timing)
    )
    assert run()["generated"] == 0
    with factory() as s:
        item = s.scalar(select(HighlightRequest))
        assert item.status == "unfulfilled"
        assert "arahan topik" in item.reason
