import json
import subprocess
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import review_audio, db, review
from app.db import Job
from test_review_workflow import data


def setup(data, monkeypatch):
    factory, pid, folder = data
    monkeypatch.setattr(review_audio, "project_dir", lambda _: folder)
    monkeypatch.setattr(review_audio, "wake", lambda: None)
    monkeypatch.setattr(db, "Session", factory)
    from app import source_cache

    monkeypatch.setattr(review_audio, "STORAGE", folder / "shared-storage")
    monkeypatch.setattr(source_cache, "STORAGE", folder / "shared-storage")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=12000",
            "-t",
            "10",
            "-c:a",
            "aac",
            str(folder / "audio.m4a"),
        ],
        check=True,
    )
    return factory, pid, folder


def test_prepare_range_and_bounded_waveform(data, monkeypatch):
    factory, pid, folder = setup(data, monkeypatch)
    result = review_audio.prepare(pid)
    with factory() as s:
        meta = review_audio.metadata(pid, s)
        assert meta.audio_status == meta.waveform_status == "ready"
        wave = review_audio.waveform(pid, 0, 300, 25, s)
        assert 1 <= len(wave.peaks) <= 25
        assert any(low < 0 < high for low, high in wave.peaks)
        source, root, key = review_audio.location(s.get(db.Project, pid))
        manifest = json.loads((root / "manifest.json").read_text())
        assert 300 <= manifest["counts"][0] <= 304  # AAC decoder padding at the final packet.
        unchanged = (root / "audio.m4a").stat().st_mtime_ns
    review_audio.prepare(pid)
    assert (root / "audio.m4a").stat().st_mtime_ns == unchanged
    app = FastAPI()
    app.include_router(review_audio.router)

    def session():
        with factory() as s:
            yield s

    app.dependency_overrides[db.session] = session
    with TestClient(app) as client:
        r = client.get(f"/api/projects/{pid}/review-audio/media", headers={"Range": "bytes=10-29"})
        assert r.status_code == 206
        assert len(r.content) == 20
        assert r.headers["content-range"].startswith("bytes 10-29/")
        assert (
            client.get(
                f"/api/projects/{pid}/review-audio/media", headers={"Range": "bytes=999999999-"}
            ).status_code
            == 416
        )
        assert (
            client.get(f"/api/projects/{pid}/review-audio/waveform?points=4097").status_code == 422
        )
        assert client.get(f"/api/projects/{pid}/review-audio/waveform?start=-1").status_code == 422


def test_idempotent_queue_and_missing_source(data, monkeypatch):
    factory, pid, folder = setup(data, monkeypatch)
    # Source identity linking must not trigger network or a download.
    with factory() as s:
        first = review_audio.request_prepare(pid, s)
        second = review_audio.request_prepare(pid, s)
        assert first.job["id"] == second.job["id"]
        assert len(list(s.scalars(select(Job).where(Job.kind == "review_audio")))) == 1
        assert s.get(db.Project, pid).status not in ("failed",)
    (folder / "audio.m4a").unlink()
    (folder / "source.mp4").unlink()
    for source in (folder / "shared-storage").rglob("*"):
        if source.name in ("audio.m4a", "source.mp4"):
            source.unlink()
    with factory() as s:
        assert review_audio.metadata(pid, s).audio_status == "missing"


def test_transcript_position_uses_same_groups(data):
    factory, pid, _ = data
    with factory() as s:
        page = review.transcript_range(pid, start=0, end=18000, position=325, limit=5, s=s)
        assert page["offset"] > 0
        assert any(g["start"] <= 325 < g["end"] for g in page["groups"])


@pytest.mark.parametrize("duration", [10, 7200, 18000])
def test_waveform_limits_for_long_sources(data, monkeypatch, duration):
    import struct

    factory, pid, folder = setup(data, monkeypatch)
    with factory() as s:
        project = s.get(db.Project, pid)
        project.duration = duration
        s.commit()
        _, root, _ = review_audio.location(project)
        root.mkdir(parents=True, exist_ok=True)
        count = duration * 30
        counts = []
        level = 0
        while True:
            counts.append(count)
            with (root / f"level-{level}.bin").open("wb") as out:
                remaining = count
                while remaining:
                    chunk = min(remaining, 4096)
                    out.write(struct.pack("<hh", -12000, 12000) * chunk)
                    remaining -= chunk
            if count == 1:
                break
            count = (count + 3) // 4
            level += 1
        (root / "manifest.json").write_text(json.dumps({"counts": counts}))
        for points in (1, 32, 4096):
            wave = review_audio.waveform(pid, 0, duration * 30, points, s)
            assert len(wave.peaks) <= points
            assert wave.start == 0
        last = review_audio.waveform(pid, max(0, duration * 30 - 300), duration * 30, 1024, s)
        assert last.peaks and last.start >= max(0, duration - 10) - 1


def test_retry_reuses_completed_audio(data, monkeypatch):
    factory, pid, folder = setup(data, monkeypatch)

    def fail(**kw):
        if kw.get("stage") == "Membuat waveform audio":
            raise RuntimeError("Simulated interruption")

    with pytest.raises(RuntimeError):
        review_audio.prepare(pid, progress=fail)
    with factory() as s:
        _, root, _ = review_audio.location(s.get(db.Project, pid))
    modified = (root / "audio.m4a").stat().st_mtime_ns
    assert not (root / "manifest.json").exists()
    review_audio.prepare(pid)
    assert (root / "audio.m4a").stat().st_mtime_ns == modified
    assert (root / "manifest.json").exists()
