import io
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, VideoClip, Instansi, Project, Job, Clip, project_instansi, session
from app.instansi_api import create, rename, remove, listing, InstansiInput, filter_sources
from app.video_library import edit, Metadata, snapshot, live_job_payload, info
from app.hashtags import filter_library
from app.schemas import ProjectInput


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s, factory
    engine.dispose()


def seed(s):
    a = Instansi(name="Cryptowave", name_key="cryptowave")
    b = Instansi(name="Akademi Crypto", name_key="akademi crypto")
    c = Instansi(name="Other", name_key="other")
    s.add_all([a, b, c])
    s.flush()
    rows = [
        VideoClip(title="Cryptowave", scope="instansi", instansi_records=[a], status="ready"),
        VideoClip(title="Akademi", scope="instansi", instansi_records=[b], status="ready"),
        VideoClip(title="Other", scope="instansi", instansi_records=[c], status="ready"),
        VideoClip(title="Global", scope="global", status="ready"),
        VideoClip(title="Not ready", scope="global", status="queued"),
    ]
    s.add_all(rows)
    s.commit()
    return a, b, c, rows


def test_crud_counts_casefold_and_referenced_deletion(db):
    s, _ = db
    a = create(InstansiInput(name="  Cryptowave  "), s)
    assert a["name"] == "Cryptowave" and a["video_count"] == 0
    with pytest.raises(HTTPException) as exc:
        create(InstansiInput(name="CRYPTOWAVE"), s)
    assert exc.value.status_code == 409
    v = VideoClip(title="A", scope="instansi", instansi_records=[s.get(Instansi, a["id"])])
    s.add(v)
    s.commit()
    assert listing(s)[0]["video_count"] == 1
    old = v.revision
    rename(a["id"], InstansiInput(name="Cryptowave Baru"), s)
    s.expire_all()
    assert v.revision == old + 1
    with pytest.raises(HTTPException) as exc:
        remove(a["id"], s)
    assert exc.value.status_code == 409 and s.get(VideoClip, v.id)
    s.rollback()
    s.delete(v)
    s.commit()
    project = Project(url="test", instansi_records=[s.get(Instansi, a["id"])])
    s.add(project)
    s.commit()
    assert listing(s)[0]["project_count"] == 1
    with pytest.raises(HTTPException):
        remove(a["id"], s)
    s.rollback()
    s.delete(project)
    s.commit()
    remove(a["id"], s)
    assert listing(s) == []


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_institution_names(name):
    with pytest.raises(ValidationError):
        InstansiInput(name=name)


def test_all_source_combinations_and_hashtag_and(db):
    s, _ = db
    a, b, c, rows = seed(s)

    def ids(owners, glob):
        return {x["id"] for x in snapshot(s, [], owners, glob)}

    assert ids([], True) == {rows[3].id} and ids([], False) == {rows[3].id}
    assert ids([a.id], False) == {rows[0].id}
    assert ids([a.id], True) == {rows[0].id, rows[3].id}
    assert ids([a.id, b.id], False) == {rows[0].id, rows[1].id}
    assert ids([a.id, b.id], True) == {rows[0].id, rows[1].id, rows[3].id}
    candidates = [
        {"id": "a", "scope": "instansi", "instansi_ids": [a.id], "hashtags": ["fory", "asek"]},
        {"id": "b", "scope": "global", "hashtags": ["fory"]},
        {"id": "c", "scope": "instansi", "instansi_ids": [c.id], "hashtags": ["fory", "asek"]},
    ]
    assert [
        x["id"] for x in filter_library(filter_sources(candidates, [a.id], True), ["fory", "asek"])
    ] == ["a"]
    assert filter_library(filter_sources(candidates, [b.id], False), ["fory", "asek"]) == []


def test_metadata_owner_revision_and_manual_sources_still_unrestricted(db):
    s, _ = db
    a, b, c, rows = seed(s)
    v = rows[0]
    body = Metadata(title=v.title, revision=v.revision, scope="global", instansi_ids=[])
    old = v.revision
    result = edit(v.id, body, s)
    assert result["scope"] == "global" and result["instansi_ids"] == []
    with pytest.raises(HTTPException) as exc:
        edit(v.id, Metadata(title=v.title, revision=old, scope="instansi", instansi_ids=[b.id]), s)
    assert exc.value.status_code == 409
    s.rollback()
    result = edit(
        v.id, Metadata(title=v.title, revision=v.revision, scope="instansi", instansi_ids=[b.id]), s
    )
    assert result["instansi_ids"] == [b.id] and result["instansi_names"] == ["Akademi Crypto"]
    with pytest.raises(HTTPException):
        edit(
            v.id,
            Metadata(title=v.title, revision=v.revision, scope="instansi", instansi_ids=[uuid4()]),
            s,
        )
    s.rollback()
    # Save validation locks any existing manual asset, regardless of institution.
    from app.video_library import lock_plan_assets

    lock_plan_assets(s, {"segments": [{"broll": [{"asset_id": rows[2].id}]}]})
    assert info(rows[2])["instansi_names"] == ["Other"]
    for kwargs in [{"scope": "instansi"}, {"scope": "global", "instansi_ids": [a.id]}]:
        with pytest.raises(ValidationError):
            Metadata(title="x", revision=1, **kwargs)


def test_project_api_pivot_and_invalid_sources(db, monkeypatch):
    from app.main import app

    s, factory = db
    a, b, c, rows = seed(s)

    def override():
        with factory() as local:
            yield local

    app.dependency_overrides[session] = override
    monkeypatch.setattr("app.main.validate_model", lambda _: None)
    try:
        with TestClient(app) as client:
            body = {
                "url": "https://youtu.be/K-iDtHzEzu8",
                "gemini_model": "gemini-test",
                "visual_mode": "mix",
                "instansi_ids": [a.id, b.id, a.id],
                "include_global": False,
            }
            response = client.post("/api/projects", json=body)
            assert response.status_code == 201, response.text
            result = response.json()
            assert set(result["instansi_ids"]) == {a.id, b.id} and result["include_global"] is False
            assert (
                client.get("/api/projects/" + result["id"]).json()["instansi_ids"]
                == result["instansi_ids"]
            )
            body["instansi_ids"] = [str(uuid4())]
            assert client.post("/api/projects", json=body).status_code == 422
            body["instansi_ids"] = []
            result = client.post("/api/projects", json=body).json()
            assert result["include_global"] is True
            assert s.scalar(select(func.count()).select_from(project_instansi)) == 2
            assert client.delete("/api/instansi/" + a.id).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_upload_requires_explicit_scope_and_valid_owner(db, monkeypatch, tmp_path):
    from app.main import app

    s, factory = db
    a, b, c, rows = seed(s)

    def override():
        with factory() as local:
            yield local

    app.dependency_overrides[session] = override
    monkeypatch.setattr("app.video_library.STORAGE", tmp_path)
    monkeypatch.setattr("app.video_library.folder", lambda aid: tmp_path / aid)
    monkeypatch.setattr("app.video_library.dispatch", lambda _: None)
    try:
        with TestClient(app) as client:
            files = {"file": ("test.mp4", b"fake video", "video/mp4")}
            assert client.post("/api/video-clips", files=files).status_code == 422
            assert (
                client.post("/api/video-clips", data={"scope": "instansi"}, files=files).status_code
                == 422
            )
            assert (
                client.post(
                    "/api/video-clips",
                    data={"scope": "instansi", "instansi_ids": [str(uuid4())]},
                    files=files,
                ).status_code
                == 422
            )
            result = client.post(
                "/api/video-clips", data={"scope": "instansi", "instansi_ids": [a.id]}, files=files
            )
            assert result.status_code == 202, result.text
            assert result.json()["instansi_ids"] == [a.id]
            result = client.post("/api/video-clips", data={"scope": "global"}, files=files)
            assert result.status_code == 202 and result.json()["instansi_ids"] == []
    finally:
        app.dependency_overrides.clear()


def test_retry_snapshot_filters_legacy_and_preserves_new_policy(db):
    s, _ = db
    a, b, c, rows = seed(s)
    p = Project(url="test", visual_mode="mix", instansi_records=[a], include_global=False)
    s.add(p)
    s.commit()
    raw = [info(v) for v in rows[:4]]
    legacy = live_job_payload(
        s,
        {
            "project_id": p.id,
            "visual_mode": "mix",
            "library": [
                {k: v for k, v in item.items() if k not in ["scope", "instansi_ids"]}
                for item in raw
            ],
        },
    )
    assert [v["id"] for v in legacy["library"]] == [rows[0].id]
    policy = {
        "project_id": p.id,
        "visual_mode": "mix",
        "source_policy_version": 1,
        "instansi_ids": [b.id],
        "include_global": True,
        "library": raw,
        "mix_hashtags": [],
    }
    filtered = live_job_payload(s, policy)
    assert {v["id"] for v in filtered["library"]} == {rows[1].id, rows[3].id}
    # The snapshot remains authoritative even if current metadata later changes.
    rows[1].instansi_records = [c]
    s.commit()
    assert {v["id"] for v in live_job_payload(s, filtered)["library"]} == {rows[1].id, rows[3].id}


def test_worker_discards_cache_outside_source_policy(db, monkeypatch):
    from app import router_ai
    from app import mix_generation
    from app.timeline import EditPlanV2

    s, factory = db
    a, b, c, rows = seed(s)
    monkeypatch.setattr(mix_generation, "Session", factory)

    def forbidden(*args, **kwargs):
        raise AssertionError("No Gemini call when no candidates")

    monkeypatch.setattr(router_ai, "generate", forbidden)
    p = Project(url="test", visual_mode="mix")
    s.add(p)
    s.flush()
    plan = EditPlanV2(segments=[{"id": "seg", "duration": 600, "source_in": 0}]).model_dump()
    clip = Clip(project_id=p.id, title="Test", plan=plan)
    s.add(clip)
    s.flush()
    cached = mix_generation.validate_suggestions(
        EditPlanV2.model_validate(plan).model_dump(),
        [{"asset_id": rows[2].id, "start": 90, "end": 180, "reason": "old", "source_in": 0}],
        [{"id": rows[2].id, "frames": 300}],
    )
    payload = {
        "source_policy_version": 1,
        "instansi_ids": [a.id],
        "include_global": False,
        "library": [{**info(rows[2]), "frames": 300}],
        "mix_target_ids": [clip.id],
        "mix_results": {clip.id: cached},
    }
    job = Job(project_id=p.id, kind="mix", payload=payload)
    s.add(job)
    s.commit()
    mix_generation.generate_mix(job.id, p.id, payload, lambda: None)
    s.expire_all()
    assert not s.get(Clip, clip.id).plan["segments"][0]["broll"]
    assert not s.get(Job, job.id).payload["mix_results"][clip.id]["segments"][0]["broll"]


@pytest.mark.parametrize(
    "which,include_global,expected",
    [
        ((), True, {3}),
        ((0,), False, {0}),
        ((0,), True, {0, 3}),
        ((0, 1), False, {0, 1}),
        ((0, 1), True, {0, 1, 3}),
    ],
)
def test_analysis_enqueue_snapshots_source_policy(db, monkeypatch, which, include_global, expected):
    from app import main

    s, _ = db
    a, b, c, rows = seed(s)
    monkeypatch.setattr(main, "validate_model", lambda _: None)
    monkeypatch.setattr(main.execute, "apply_async", lambda **_: None)
    owners = [a, b, c]
    project = Project(
        url="test",
        visual_mode="mix",
        gemini_model="gemini-test",
        instansi_records=[owners[i] for i in which],
        include_global=include_global,
    )
    s.add(project)
    s.commit()
    job = main.analysis(project.id, s)
    assert job["payload"]["source_policy_version"] == 1
    assert set(job["payload"]["instansi_ids"]) == {owners[i].id for i in which}
    assert {v["id"] for v in job["payload"]["library"]} == {rows[i].id for i in expected}
    saved = s.get(Job, job["id"])
    saved.status = "failed"
    s.commit()
    original = saved.payload
    project.instansi_records = [c]
    project.include_global = False
    s.commit()
    retried = main.retry_mix(project.id, s)
    assert retried["payload"]["instansi_ids"] == original["instansi_ids"]
    assert {v["id"] for v in retried["payload"]["library"]} == {rows[i].id for i in expected}


def test_shared_video_matches_either_institution_once_and_can_detach(db):
    from app.db import instasi_to_video_clips

    s, _ = db
    a, b, c, rows = seed(s)
    shared = VideoClip(
        title="CEO collaboration",
        scope="instansi",
        instansi_records=[a, b],
        status="ready",
        duration=6,
    )
    s.add(shared)
    s.commit()
    assert set(info(shared)["instansi_ids"]) == {a.id, b.id}
    for ids in [[a.id], [b.id], [a.id, b.id]]:
        matches = snapshot(s, [], ids, False)
        assert [x["id"] for x in matches].count(shared.id) == 1
    assert shared.id not in {x["id"] for x in snapshot(s, [], [c.id], False)}
    assert shared.id not in {x["id"] for x in snapshot(s, [], [], True)}
    counts = {x["id"]: x["video_count"] for x in listing(s)}
    assert counts[a.id] == 2 and counts[b.id] == 2
    result = edit(
        shared.id,
        Metadata(
            title=shared.title,
            revision=shared.revision,
            scope="instansi",
            instansi_ids=[a.id, b.id, a.id],
        ),
        s,
    )
    assert len(result["instansi_ids"]) == 2
    assert (
        s.scalar(
            select(func.count())
            .select_from(instasi_to_video_clips)
            .where(instasi_to_video_clips.c.video_clip_id == shared.id)
        )
        == 2
    )
    with pytest.raises(HTTPException) as exc:
        remove(b.id, s)
    assert exc.value.status_code == 409
    s.rollback()
    result = edit(
        shared.id,
        Metadata(
            title=shared.title, revision=shared.revision, scope="instansi", instansi_ids=[a.id]
        ),
        s,
    )
    assert result["instansi_ids"] == [a.id] and s.get(VideoClip, shared.id) is not None
    assert shared.id not in {x["id"] for x in snapshot(s, [], [b.id], False)}
    result = edit(
        shared.id,
        Metadata(title=shared.title, revision=shared.revision, scope="global", instansi_ids=[]),
        s,
    )
    assert result["instansi_ids"] == [] and result["scope"] == "global"
    assert (
        s.scalar(
            select(func.count())
            .select_from(instasi_to_video_clips)
            .where(instasi_to_video_clips.c.video_clip_id == shared.id)
        )
        == 0
    )
    s.delete(shared)
    s.commit()
    assert s.get(Instansi, a.id) and s.get(Instansi, b.id)


def test_multipart_upload_multiple_institutions(db, monkeypatch, tmp_path):
    from app.main import app

    s, factory = db
    a, b, c, rows = seed(s)

    def override():
        with factory() as local:
            yield local

    app.dependency_overrides[session] = override
    monkeypatch.setattr("app.video_library.STORAGE", tmp_path)
    monkeypatch.setattr("app.video_library.folder", lambda aid: tmp_path / aid)
    monkeypatch.setattr("app.video_library.dispatch", lambda _: None)
    try:
        with TestClient(app) as client:
            files = {"file": ("test.mp4", b"fixture", "video/mp4")}
            result = client.post(
                "/api/video-clips",
                data={"scope": "instansi", "instansi_ids": [a.id, b.id, a.id]},
                files=files,
            )
            assert result.status_code == 202, result.text
            assert set(result.json()["instansi_ids"]) == {a.id, b.id}
            assert result.json()["instansi_names"] == ["Akademi Crypto", "Cryptowave"]
            bad = client.post(
                "/api/video-clips", data={"scope": "global", "instansi_ids": [a.id]}, files=files
            )
            assert bad.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_pre_pivot_snapshots_keep_their_original_membership():
    old = [{"id": "shared-now", "scope": "instansi", "instansi_id": "cryptowave"}]
    assert filter_sources(old, ["cryptowave"], False) == old
    assert filter_sources(old, ["stockwise"], False) == []
    new = [{"id": "shared-now", "scope": "instansi", "instansi_ids": ["cryptowave", "stockwise"]}]
    assert filter_sources(new, ["stockwise"], False) == new
    assert len(filter_sources(new, ["cryptowave", "stockwise"], False)) == 1
