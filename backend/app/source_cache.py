"""Shared source cache with private project links and resumable downloads."""

import json
import math
import os
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from sqlalchemy import select, text
from .config import STORAGE
from .db import Session, Project, MediaSource
from .media import probe, run, write_json


class DownloadWait(Exception):
    pass


def source_record(session, project):
    if project.source_id:
        return session.get(MediaSource, project.source_id)
    from .schemas import youtube_url

    video = parse_qs(urlsplit(youtube_url(project.url)).query)["v"][0]
    if session.bind.dialect.name == "postgresql":
        import hashlib

        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock)"),
            {"lock": int(hashlib.sha256(video.encode()).hexdigest()[:15], 16)},
        )
    record = session.scalar(select(MediaSource).where(MediaSource.youtube_id == video))
    if record is None:
        record = MediaSource(youtube_id=video, url=project.url)
        session.add(record)
        session.flush()
    project.source_id = record.id
    session.flush()
    return record


def link_file(source, target):
    if target.exists() or target.is_symlink():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source.resolve())


def shared_folder(pid, private, db_session=None, storage=None):
    from contextlib import nullcontext

    context = nullcontext(db_session) if db_session is not None else Session()
    with context as session:
        project = session.scalar(select(Project).where(Project.id == pid).with_for_update())
        record = source_record(session, project)
        root = (storage or STORAGE) / "sources" / record.id
        root.mkdir(parents=True, exist_ok=True)
        if db_session is None:
            session.commit()
    # Register old complete media using hard links, retaining the original files.
    for name in ("source.mp4", "metadata.json", "transcript.json"):
        old, cached = private / name, root / name
        if old.is_file() and not old.is_symlink() and not cached.exists():
            try:
                os.link(old, cached)
            except FileExistsError:
                pass
        if cached.exists():
            link_file(cached, old)
    return root


def inspect(path, audio_only=False):
    data = probe(path)
    kinds = {s["codec_type"] for s in data["streams"]}
    duration = float(data["format"].get("duration", 0))
    if (
        "audio" not in kinds
        or (not audio_only and "video" not in kinds)
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise RuntimeError(
            "Sumber unduhan belum lengkap atau tidak memiliki stream yang diperlukan."
        )
    return duration


def download(root, url, video, check, update):
    import yt_dlp

    target = root / ("source.mp4" if video else "audio.m4a")
    if target.exists():
        duration = inspect(target, not video)
        metadata = root / "metadata.json"
        if not metadata.exists():
            prior = root / ("video-download.json" if video else "audio-download.json")
            try:
                saved = json.loads(prior.read_text())
            except (OSError, ValueError):
                saved = {}
            write_json(
                metadata, {"title": saved.get("title", "Video YouTube"), "duration": duration}
            )
        return target
    manifest_path = root / ("video-download.json" if video else "audio-download.json")
    stem = "video" if video else "audio"
    last = [0.0]
    label = "video sumber" if video else "audio sumber"

    def hook(data):
        check()
        if time.monotonic() - last[0] < 1 and data["status"] != "finished":
            return
        last[0] = time.monotonic()
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        values = {
            "downloaded_bytes": data.get("downloaded_bytes", 0),
            "download_total_bytes": total,
            "download_speed": data.get("speed"),
            "eta_seconds": data.get("eta"),
        }
        update(stage="Mengunduh " + label, metrics=values)

    options = {
        "format": (
            "bv*[height<=1080]/b[height<=1080]"
            if (root / "audio.m4a").exists()
            else "bv*[height<=1080]+ba/b[height<=1080]"
        )
        if video
        else "bestaudio/best",
        "outtmpl": str(root / (stem + ".%(format_id)s.%(ext)s")),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "socket_timeout": 60,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 1,
        "skip_unavailable_fragments": False,
        "continuedl": True,
        "overwrites": False,
        "progress_hooks": [hook],
        "retry_sleep_functions": {
            "http": lambda n: min(30, 2**n),
            "fragment": lambda n: min(30, 2**n),
        },
        "js_runtimes": {"node": {}},
    }
    try:
        update(stage="Mengambil informasi YouTube")
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("is_live") or info.get("live_status") == "is_upcoming":
                raise RuntimeError("Live stream belum didukung.")
            if not info.get("duration"):
                raise RuntimeError("Durasi sumber tidak tersedia.")
            if shutil.disk_usage(root).free < max(
                256 * 1024**2, (info.get("filesize") or info.get("filesize_approx") or 0) * 2
            ):
                raise RuntimeError("Ruang disk tidak cukup untuk unduhan.")
            write_json(
                manifest_path,
                {
                    "version": 1,
                    "youtube_id": info["id"],
                    "title": info.get("title", "Video YouTube"),
                    "duration": info["duration"],
                    "complete": False,
                    "formats": [r.get("format_id") for r in info.get("requested_formats", [info])],
                },
            )
            # yt-dlp's format-specific filenames keep incompatible partials separate.
            result = ydl.process_ie_result(info, download=True)
            check()
        requested = result.get("requested_downloads", [])
        candidates = [Path(x["filepath"]) for x in requested if x.get("filepath")]
        candidates += sorted(root.glob(stem + ".*"))
        candidates = [
            p
            for p in candidates
            if p.suffix in (".mp4", ".m4a", ".webm", ".mkv", ".opus", ".mp3") and p.is_file()
        ]
        if not candidates:
            raise RuntimeError("File unduhan belum ditemukan setelah pengunduhan.")
        selected = next(
            (
                p
                for p in candidates
                if video and any(s["codec_type"] == "video" for s in probe(p)["streams"])
            ),
            candidates[0],
        )
        update(stage="Menggabungkan video dan audio" if video else "Menyiapkan audio sumber")
        temporary = target.with_name(target.stem + ".partial" + target.suffix)
        args = ["ffmpeg", "-y", "-v", "error", "-i", str(selected)]
        if video:
            # Use the original download audio when the video is a separate stream.
            kinds = {s["codec_type"] for s in probe(selected)["streams"]}
            audio = root / "audio.m4a"
            if "audio" not in kinds and audio.exists():
                args += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0"]
            args += ["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"]
        else:
            args += ["-vn", "-c:a", "aac", "-b:a", "128k"]
        run(args + [str(temporary)], check)
        duration = inspect(temporary, not video)
        expected = float(info["duration"])
        if abs(duration - expected) > max(2, expected * 0.001):
            raise RuntimeError(
                "Durasi unduhan tidak sesuai sumber. Berkas parsial disimpan untuk diperiksa."
            )
        temporary.replace(target)
        write_json(
            root / "metadata.json",
            {"title": info.get("title", "Video YouTube"), "duration": duration},
        )
        write_json(
            manifest_path,
            {"version": 1, "youtube_id": info["id"], "complete": True, "duration": duration},
        )
        return target
    except yt_dlp.utils.DownloadError as error:
        text = str(error).lower()
        if any(
            term in text
            for term in (
                "private video",
                "video unavailable",
                "removed",
                "sign in",
                "not available in your country",
            )
        ):
            raise RuntimeError(
                "Sumber YouTube tidak tersedia atau memerlukan autentikasi."
            ) from error
        raise DownloadWait(
            "Unduhan terputus. Berkas parsial disimpan dan akan dilanjutkan ketika jaringan pulih."
        ) from error


def prepare(pid, private, url, video, check, update):
    root = shared_folder(pid, private)
    if not video and (root / "transcript.json").exists():
        metadata = json.loads((root / "metadata.json").read_text())
        return root, None, float(metadata.get("duration") or inspect(root / "source.mp4"))
    available = root / "source.mp4"
    if available.exists():
        duration = inspect(available)
        source = available
    else:
        source = download(root, url, video, check, update)
        duration = inspect(source, not video)
    for name in ("source.mp4", "metadata.json", "transcript.json"):
        if (root / name).exists():
            link_file(root / name, private / name)
    return root, source, duration
