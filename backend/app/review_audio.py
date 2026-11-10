"""Bounded-memory source audio and multiresolution waveform for proposal review."""

import array
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from .config import STORAGE
from .db import Job, Project, session
from .media import project_dir, probe, run, write_json
from .queue_runtime import PENDING, public_job, wake

router = APIRouter(prefix="/api/projects")
VERSION = 1


def location(project):
    private = project_dir(project.id)
    root = STORAGE / "sources" / project.source_id if project.source_id else private
    source = next(
        (
            p
            for p in (
                root / "audio.m4a",
                root / "source.mp4",
                private / "audio.m4a",
                private / "source.mp4",
            )
            if p.is_file()
        ),
        None,
    )
    if source is None:
        return None, None, None
    source = source.resolve()
    stat = source.stat()
    key = hashlib.sha256(
        f"{VERSION}:{source}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    ).hexdigest()
    return source, source.parent / "review-audio" / key, key


def project_for(s, pid, lock=False):
    stmt = select(Project).where(Project.id == pid)
    if lock:
        stmt = stmt.with_for_update()
    project = s.scalar(stmt)
    if not project:
        raise HTTPException(404, "Proyek tidak ditemukan.")
    return project


class AudioState(BaseModel):
    audio_status: str
    waveform_status: str
    duration: float
    audio_url: str | None = None
    version: str | None = None
    job: dict | None = None
    error: str | None = None


def state(s, project):
    source, folder, key = location(project)
    if not source:
        return AudioState(
            audio_status="missing",
            waveform_status="missing",
            duration=project.duration,
            error="Audio dan video sumber tidak tersedia. Gunakan tautan YouTube untuk memeriksa bagian ini.",
        )
    job = s.scalar(
        select(Job)
        .where(Job.kind == "review_audio", Job.payload["source_key"].as_string() == key)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return AudioState(
        audio_status="ready" if (folder / "audio.m4a").is_file() else "pending",
        waveform_status="ready" if (folder / "manifest.json").is_file() else "pending",
        duration=project.duration,
        audio_url=f"/api/projects/{project.id}/review-audio/media",
        version=key,
        job=public_job(s, job) if job else None,
        error=job.error if job and job.status == "failed" else None,
    )


@router.get("/{pid}/review-audio", response_model=AudioState)
def metadata(pid: str, s=Depends(session)):
    return state(s, project_for(s, pid))


@router.post("/{pid}/review-audio", response_model=AudioState)
def request_prepare(pid: str, s=Depends(session)):
    project = project_for(s, pid, True)
    from .source_cache import source_record

    # Serialize requests from all projects sharing this source.
    record = source_record(s, project)
    from .db import MediaSource

    s.execute(select(MediaSource).where(MediaSource.id == record.id).with_for_update()).scalar_one()
    from .source_cache import shared_folder

    root = shared_folder(pid, project_dir(pid), db_session=s)
    private_audio = project_dir(pid) / "audio.m4a"
    if private_audio.is_file() and not (root / "audio.m4a").exists():
        os.link(private_audio.resolve(), root / "audio.m4a")
    source, folder, key = location(project)
    if source is None:
        raise HTTPException(
            409, "Audio dan video sumber tidak tersedia; tidak mengunduh ulang otomatis."
        )
    existing = s.scalar(
        select(Job)
        .where(
            Job.kind == "review_audio",
            Job.status.in_(PENDING),
            Job.payload["source_key"].as_string() == key,
        )
        .limit(1)
    )
    if not (folder / "manifest.json").is_file() and not existing:
        s.add(Job(project_id=pid, kind="review_audio", payload={"source_key": key}))
    s.commit()
    wake()
    return state(s, project)


@router.get("/{pid}/review-audio/media")
def media(pid: str, s=Depends(session)):
    project = project_for(s, pid)
    _, folder, _ = location(project)
    if folder is None or not (folder / "audio.m4a").is_file():
        raise HTTPException(404, "Audio belum siap.")
    return FileResponse(folder / "audio.m4a", media_type="audio/mp4")


class Waveform(BaseModel):
    start: float
    step: float
    peaks: list[tuple[int, int]]
    version: str


@router.get("/{pid}/review-audio/waveform", response_model=Waveform)
def waveform(
    pid: str,
    start: int = 0,
    end: int | None = None,
    points: int = Query(1024, ge=1, le=4096),
    s=Depends(session),
):
    project = project_for(s, pid)
    end = end if end is not None else math.floor(project.duration * 30)
    if start < 0 or end <= start or end > math.floor(project.duration * 30 + 0.00001):
        raise HTTPException(422, "Rentang waveform di luar sumber.")
    _, folder, key = location(project)
    if folder is None or not (folder / "manifest.json").is_file():
        raise HTTPException(409, "Waveform belum siap.")
    meta = json.loads((folder / "manifest.json").read_text())
    level = 0
    while (
        level + 1 < len(meta["counts"]) and math.ceil(end / 4**level) - start // 4**level > points
    ):
        level += 1
    step = 4**level
    first, last = start // step, math.ceil(end / step)
    with (folder / f"level-{level}.bin").open("rb") as f:
        f.seek(first * 4)
        raw = f.read(min(4096, last - first) * 4)
    return Waveform(
        start=first * step / 30,
        step=step / 30,
        peaks=list(struct.iter_unpack("<hh", raw)),
        version=key,
    )


def prepare(pid, check=lambda: None, progress=lambda **kw: None):
    from .db import Session

    with Session() as s:
        project = project_for(s, pid)
        source, folder, key = location(project)
    if source is None:
        raise RuntimeError("Audio dan video sumber tidak tersedia.")
    folder.mkdir(parents=True, exist_ok=True)
    audio = folder / "audio.m4a"
    if not audio.exists():
        progress(stage="Menyiapkan audio sumber", progress=10)
        codec = next(
            x["codec_name"] for x in probe(source)["streams"] if x["codec_type"] == "audio"
        )
        temp = folder / "audio.partial.m4a"
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-threads",
                "2",
                "-i",
                str(source),
                "-vn",
                "-c:a",
                "copy" if codec == "aac" else "aac",
                "-movflags",
                "+faststart",
                str(temp),
            ],
            check,
        )
        check()
        temp.replace(audio)
    if (folder / "manifest.json").exists():
        return {"version": key}
    progress(stage="Membuat waveform audio", progress=35)
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-threads",
        "2",
        "-i",
        str(audio),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "12000",
        "-f",
        "s16le",
        "-",
    ]
    kwargs = (
        {"pass_fds": (int(os.environ["VC_HEAVY_LOCK_FD"]),)}
        if os.environ.get("VC_HEAVY_LOCK_FD")
        else {}
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kwargs)
    counts = []
    last_check = 0.0

    def bounded_check():
        nonlocal last_check
        if time.monotonic() - last_check > 0.25:
            check()
            last_check = time.monotonic()

    try:
        count = 0
        temp = folder / "level-0.partial"
        with temp.open("wb") as f:
            while True:
                bounded_check()
                raw = process.stdout.read(800)
                if not raw:
                    break
                values = array.array("h")
                values.frombytes(raw[: len(raw) // 2 * 2])
                if sys.byteorder != "little":
                    values.byteswap()
                f.write(struct.pack("<hh", min(values, default=0), max(values, default=0)))
                count += 1
        if process.wait() != 0:
            raise RuntimeError("Pembuatan waveform gagal.")
        check()
        temp.replace(folder / "level-0.bin")
        counts.append(count)
        level = 0
        while count > 1:
            check()
            temp = folder / f"level-{level + 1}.partial"
            with (folder / f"level-{level}.bin").open("rb") as src, temp.open("wb") as out:
                while raw := src.read(16):
                    bounded_check()
                    pairs = list(struct.iter_unpack("<hh", raw))
                    out.write(
                        struct.pack("<hh", min(x[0] for x in pairs), max(x[1] for x in pairs))
                    )
            count = math.ceil(count / 4)
            level += 1
            temp.replace(folder / f"level-{level}.bin")
            counts.append(count)
        write_json(folder / "manifest.partial.json", {"version": VERSION, "counts": counts})
        check()
        (folder / "manifest.partial.json").replace(folder / "manifest.json")
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
        process.stdout.close()
    return {"version": key}
