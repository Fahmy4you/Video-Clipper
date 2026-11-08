"""Small resource and phase diagnostics; never logs payloads or credentials."""

import json, logging, os, time
from datetime import datetime, timezone
from pathlib import Path
from .config import STORAGE

log = logging.getLogger("video_clipping.jobs")


def event(name, **fields):
    log.info(json.dumps({"event": name, **fields}, ensure_ascii=False, default=str))


def phase_for(stage):
    for prefix, phase in [
        ("Memeriksa subtitle", "subtitle_refinement"),
        ("Menyiapkan Whisper small", "subtitle_refinement"),
        ("Mengunduh", "download"),
        ("Menggabungkan", "merge"),
        ("Memeriksa sumber", "source_probe"),
        ("Mengekstrak", "audio"),
        ("Menyiapkan model", "transcription"),
        ("Transkripsi", "transcription"),
        ("Memilih highlight", "highlights"),
        ("Menyusun video", "mix"),
        ("Merender", "render"),
        ("Menyiapkan proxy", "editor_media"),
    ]:
        if stage.startswith(prefix):
            return phase
    return None


def measure(old, stage=None, metrics=None, terminal=False):
    value = dict(old or {})
    tick = time.time()
    iso = datetime.now(timezone.utc).isoformat()
    value.setdefault("started_at", iso)
    value.setdefault("started_timestamp", tick)
    value["elapsed_seconds"] = round(tick - value["started_timestamp"], 2)
    phase = phase_for(stage or "")
    if phase and phase != value.get("phase"):
        durations = dict(value.get("phase_seconds", {}))
        if value.get("phase"):
            durations[value["phase"]] = round(
                durations.get(value["phase"], 0) + tick - value.get("phase_timestamp", tick), 2
            )
        value.update(
            phase=phase, phase_started_at=iso, phase_timestamp=tick, phase_seconds=durations
        )
    if metrics:
        peak = max(value.get("peak_memory_bytes", 0), metrics.get("peak_memory_bytes", 0))
        value.update(metrics)
        if peak:
            value["peak_memory_bytes"] = peak
    if terminal and value.get("phase"):
        durations = dict(value.get("phase_seconds", {}))
        name = value["phase"]
        durations[name] = round(
            durations.get(name, 0) + tick - value.get("phase_timestamp", tick), 2
        )
        value.update(phase_seconds=durations, finished_at=iso, phase_timestamp=tick)
    return value


def process_rss(pid):
    """RSS of the child tree. Linux /proc, no heavyweight monitoring dependency."""
    total = 0
    seen = set()
    todo = [int(pid)]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            status = Path(f"/proc/{current}/status").read_text()
            rss = next(line for line in status.splitlines() if line.startswith("VmRSS:"))
            total += int(rss.split()[1]) * 1024
            children = Path(f"/proc/{current}/task/{current}/children").read_text()
            todo.extend(int(child) for child in children.split())
        except (OSError, StopIteration):
            pass
    return total


def memory_limit():
    info = Path("/proc/meminfo").read_text()
    total = (
        int(next(line for line in info.splitlines() if line.startswith("MemTotal:")).split()[1])
        * 1024
    )
    return min(2 * 1024**3, int(total * 0.6))


def worker_health():
    try:
        data = json.loads((STORAGE / "runtime/worker.json").read_text())
        if time.time() - data.get("updated", 0) > 15:
            return {
                "status": "unavailable",
                "message": "Launcher tidak aktif. Jalankan kembali npm run dev.",
            }
        return {k: data.get(k) for k in ("status", "message", "restart_count", "next_restart_at")}
    except (OSError, ValueError):
        return {"status": "unknown", "message": "Status worker belum tersedia."}
