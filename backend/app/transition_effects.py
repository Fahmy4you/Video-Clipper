"""Built-in effects, shared deterministic flash raster and sample-accurate sound events."""

import math, wave
from pathlib import Path
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ASSETS = Path(__file__).parent / "assets" / "effects"
RATE = 48000
router = APIRouter(prefix="/api/transition-effects", tags=["transition-effects"])


class EffectView(BaseModel):
    id: str
    name: str
    audio_url: str
    duration: float
    samples: int
    sample_rate: int


@lru_cache(maxsize=1)
def audio_info():
    with wave.open(str(ASSETS / "camera_shutter.wav"), "rb") as w:
        return w.getnframes(), w.getframerate()


@router.get("", response_model=list[EffectView])
def catalog():
    samples, rate = audio_info()
    return [
        dict(
            id="camera_shutter",
            name="Camera shutter",
            audio_url="/api/transition-effects/camera_shutter/audio",
            duration=samples / rate,
            samples=samples,
            sample_rate=rate,
        )
    ]


@router.get("/{effect_id}/audio")
def audio(effect_id: str):
    if effect_id != "camera_shutter":
        raise HTTPException(404, "Efek tidak dikenal.")
    return FileResponse(ASSETS / "camera_shutter.wav", media_type="audio/wav")


def global_items(plan):
    items = []
    offset = 0
    for s in plan["segments"]:
        items.extend(
            dict(b, start=b["start"] + offset, end=b["end"] + offset) for b in s.get("broll", [])
        )
        offset += s["duration"]
    return items, offset


def edge_events(items):
    return [
        dict(
            frame=b["end" if out else "start"],
            out=out,
            item=b,
            edge=b.get("transition_out" if out else "transition_in", {}),
        )
        for b in items
        for out in (False, True)
    ]


def select_edges(events, predicate):
    chosen = {}
    for e in events:
        if predicate(e["edge"]) and (e["frame"] not in chosen or e["out"]):
            chosen[e["frame"]] = e
    return sorted(chosen.values(), key=lambda e: e["frame"])


def flashes(items, duration):
    # A source-continuous split with no internal transition is not a new visual boundary.
    merged = []
    for item in sorted(items, key=lambda b: b["start"]):
        last = merged[-1] if merged else None
        if (
            last
            and last["end"] == item["start"]
            and last["asset_id"] == item["asset_id"]
            and last["source_in"] + last["end"] - last["start"] == item["source_in"]
            and last.get("transform") == item.get("transform")
            and all(
                e.get("kind", "none") == "none" and e.get("sound", "none") == "none"
                for e in (last.get("transition_out", {}), item.get("transition_in", {}))
            )
        ):
            last.update(end=item["end"], transition_out=item.get("transition_out", {}))
        else:
            merged.append(dict(item))
    edges = edge_events(merged)
    bounds = sorted(set([0, duration] + [e["frame"] for e in edges]))
    result = []
    for e in select_edges(edges, lambda edge: edge.get("kind") == "flash"):
        f = e["frame"]
        requested = e["edge"].get("frames", 9) / 2
        distance = min([abs(f - b) / 2 for b in bounds if b != f] or [0])
        half = math.floor(
            min(requested, f, duration - f, distance, (e["item"]["end"] - e["item"]["start"]) / 2)
        )
        result.append(dict(frame=f, half=half, requested=requested))
    return result


@lru_cache(maxsize=128)
def flash_field(progress):
    p = max(0, min(1, progress))
    ease = p * p * (3 - 2 * p)
    envelope = math.sin(math.pi * p) ** 2
    cx = -0.15 + 1.3 * ease
    data = []
    for y in range(64):
        for x in range(96):
            u, v = x / 95, y / 63
            glow = math.exp(-(((u - cx) / 0.75) ** 2 + ((v - 0.42) / 0.95) ** 2))
            secondary = math.exp(-(((u - (1 - cx)) / 0.95) ** 2 + ((v - 0.85) / 0.8) ** 2))
            alpha = 0.6 * envelope * min(1, 0.22 + 0.6 * glow + 0.18 * secondary)
            data.extend(
                (
                    255,
                    math.floor(218 + 25 * glow + 0.5),
                    math.floor(188 + 31 * glow + 0.5),
                    math.floor(alpha * 255 + 0.5),
                )
            )
    return bytes(data)


def flash_strip(progress):
    # Retained for callers that only need a horizontal sample; production uses the full field.
    from PIL import Image

    return (
        Image.frombytes("RGBA", (96, 64), flash_field(progress))
        .resize((256, 1), Image.Resampling.BILINEAR)
        .tobytes()
    )


def sound_events(items):
    return [
        dict(frame=e["frame"], volume=e["edge"].get("sound_volume", 1))
        for e in select_edges(
            edge_events(items), lambda edge: edge.get("sound", "none") == "camera_shutter"
        )
    ]


def sound_windows(plan):
    items, duration = global_items(plan)
    samples, rate = audio_info()
    end = duration * rate // 30
    result = []
    if plan.get("transition_version") == 1:
        from .boundaries import boundaries

        selected = [
            dict(frame=e["frame"], volume=e["value"].get("sound_volume", 1))
            for e in boundaries(plan)
            if e["value"].get("sound") == "camera_shutter"
        ]
    else:
        selected = sound_events(items)
    for e in selected:
        raw = math.floor(e["frame"] * rate / 30 - samples / 2 + 0.5)
        skip = max(0, -raw)
        start = max(0, raw)
        length = min(samples - skip, end - start)
        if length > 0:
            result.append(
                dict(start=start, skip=skip, length=length, volume=e["volume"], frame=e["frame"])
            )
    return result


def plan_flashes(plan):
    if plan.get("transition_version") != 1:
        items, duration = global_items(plan)
        return flashes(items, duration)
    from .boundaries import events

    return [e for e in events(plan) if e["kind"] == "flash"]
