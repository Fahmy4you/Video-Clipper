"""Server-owned export dimensions and renderer identity."""

from typing import Literal
from pydantic import BaseModel, ConfigDict

RENDER_VERSION = "subtitle-templates-4"
from .timeline import RESOLUTIONS


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: Literal[360, 720, 1080] = 1080


def dimensions(ratio, resolution=1080):
    width, height = RESOLUTIONS[ratio]
    return round(width * resolution / 1080 / 2) * 2, round(height * resolution / 1080 / 2) * 2


def render_identity(source, plan, ratio, resolution):
    """Invalidate checkpoint reuse when the edit, renderer or any input changes."""
    import hashlib, json
    from pathlib import Path
    from uuid import UUID
    from .config import STORAGE

    paths = {Path(source)}
    for segment in plan.get("segments", []):
        for broll in segment.get("broll", []):
            paths.add(STORAGE / "video-clips" / str(UUID(broll["asset_id"])) / "source.media")
        for overlay in segment.get("overlays", []):
            if overlay.get("asset_id"):
                paths.add(source.parent / "assets" / (str(UUID(overlay["asset_id"])) + ".png"))
        for audio in segment.get("audio", []):
            paths.add(source.parent / "audio" / (str(UUID(audio["asset_id"])) + ".m4a"))
    sources = []
    for path in sorted(paths):
        stat = path.stat()
        sources.append((str(path), stat.st_size, stat.st_mtime_ns))
    body = {
        "renderer": RENDER_VERSION,
        "plan": plan,
        "ratio": ratio,
        "resolution": resolution,
        "sources": sources,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
