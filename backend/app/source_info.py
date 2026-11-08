"""Metadata-only source validation, shared by preflight and project submission."""

import math
import threading
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from .config import settings
from .db import Session, Project
from .schemas import youtube_url

router = APIRouter(prefix="/api")
_cache = {}
_lock = threading.Lock()
MAX_DURATION = 18000


def validate_duration(duration):
    minimum = settings.source_min_duration_seconds
    if not 1 <= minimum <= MAX_DURATION:
        raise HTTPException(503, "SOURCE_MIN_DURATION_SECONDS harus antara 1 dan 18000.")
    minimum = max(10, minimum)
    if not duration or not math.isfinite(duration):
        raise HTTPException(422, "Durasi video belum diketahui. Coba periksa sumber kembali.")
    if duration < minimum:
        raise HTTPException(422, f"Minimal video yang dianalisis adalah {minimum} detik.")
    if duration > MAX_DURATION:
        raise HTTPException(422, "Durasi video maksimal 5 jam.")
    return duration


def inspect_source(url):
    canonical = youtube_url(url)
    with _lock:
        cached = _cache.get(canonical)
        if cached and time.monotonic() - cached[0] < 300:
            result = dict(cached[1])
            validate_duration(result["duration"])
            return result
    with Session() as s:
        existing = s.scalar(
            select(Project)
            .where(Project.url == canonical, Project.duration > 0)
            .order_by(Project.updated_at.desc())
        )
        result = (
            {"url": canonical, "title": existing.title, "duration": existing.duration}
            if existing
            else None
        )
    if result is None:
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    "socket_timeout": 15,
                    "retries": 1,
                    "extractor_retries": 1,
                    "js_runtimes": {"node": {}},
                }
            ) as ydl:
                info = ydl.extract_info(canonical, download=False)
            if info.get("is_live") or info.get("live_status") in (
                "is_live",
                "is_upcoming",
                "post_live",
            ):
                raise HTTPException(422, "Gunakan video yang sudah selesai, bukan siaran live.")
            result = {
                "url": canonical,
                "title": info.get("title", "Video YouTube"),
                "duration": float(info.get("duration") or 0),
            }
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                503, "Informasi YouTube belum dapat dibaca. Periksa koneksi lalu coba lagi."
            ) from error
    validate_duration(result["duration"])
    result.update(
        min_duration=max(10, settings.source_min_duration_seconds), max_duration=MAX_DURATION
    )
    with _lock:
        _cache[canonical] = (time.monotonic(), dict(result))
    return result


class SourceInput(BaseModel):
    url: str


class SourceMetadata(BaseModel):
    url: str
    title: str
    duration: float
    min_duration: int
    max_duration: int


@router.post("/sources/inspect", response_model=SourceMetadata)
def source_metadata(body: SourceInput):
    try:
        return inspect_source(body.url)
    except ValueError as error:
        raise HTTPException(422, "URL YouTube tidak valid.") from error
