from copy import deepcopy
from uuid import uuid4
import json, subprocess, wave
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.timeline import EditPlanV2, Transition, RESOLUTIONS
from app.transition_effects import (
    router,
    audio_info,
    catalog,
    ASSETS,
    flashes,
    global_items,
    sound_events,
    sound_windows,
    flash_strip,
    flash_field,
)
from app.render_v2 import render_v2, overlay_image
from app.media import probe


def plan():
    p = EditPlanV2(segments=[{"id": "s", "source_in": 0, "duration": 360}]).model_dump()
    b = {
        "id": "b",
        "asset_id": str(uuid4()),
        "start": 300,
        "end": 330,
        "source_in": 0,
        "transition_in": {
            "kind": "flash",
            "frames": 12,
            "sound": "camera_shutter",
            "sound_volume": 0.5,
        },
        "transition_out": {"kind": "none", "frames": 0},
    }
    p["segments"][0]["broll"] = [b]
    return EditPlanV2.model_validate(p).model_dump()


def test_defaults_validation_and_asset_api():
    assert Transition().sound == "none" and Transition().sound_volume == 1
    for payload in [{"sound": "../secret"}, {"sound_volume": 2}, {"kind": "secret"}]:
        with pytest.raises(ValidationError):
            Transition(**payload)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    row = c.get("/api/transition-effects").json()[0]
    assert row["samples"] == 12261 and row["sample_rate"] == 48000
    assert row["duration"] == pytest.approx(0.2554375)
    response = c.get(row["audio_url"], headers={"Range": "bytes=0-63"})
    assert response.status_code == 206 and response.headers["content-type"] == "audio/wav"
    assert c.get("/api/transition-effects/not-an-id/audio").status_code == 404


def test_center_sample_rounding_and_clipped_edges():
    p = plan()
    e = sound_windows(p)[0]
    assert e["start"] == 473870 and e["length"] == 12261 and e["skip"] == 0
    assert abs(e["start"] + e["length"] / 2 - 480000) <= 0.5
    b = p["segments"][0]["broll"][0]
    b["start"] = 0
    b["end"] = 360
    b["transition_out"] = {"sound": "camera_shutter"}
    a, z = sound_windows(p)
    assert a["start"] == 0 and a["skip"] == 6130
    assert z["start"] + z["length"] == 360 * 1600
    assert a["length"] + a["skip"] == 12261


def test_same_boundary_prefers_outgoing_and_sound_independent():
    p = plan()
    b = p["segments"][0]["broll"][0]
    b["transition_in"]["kind"] = "none"
    b["transition_out"] = {"kind": "none", "sound": "camera_shutter", "sound_volume": 0.2}
    c = deepcopy(b)
    c.update(id="c", start=330, end=350)
    c["transition_in"]["sound_volume"] = 0.8
    p["segments"][0]["broll"].append(c)
    items, d = global_items(p)
    ev = sound_events(items)
    assert len([e for e in ev if e["frame"] == 330]) == 1
    assert next(e for e in ev if e["frame"] == 330)["volume"] == 0.2
    assert not flashes(items, d)
    b["transition_in"].pop("sound")
    assert len(sound_events(global_items(p)[0])) == 2


def test_flash_envelope_and_shortening():
    p = plan()
    items, d = global_items(p)
    assert flashes(items, d) == [{"frame": 300, "half": 6, "requested": 6}]
    items[0]["end"] = 304
    assert flashes(items, d)[0]["half"] == 2
    assert not any(flash_strip(0)[3::4]) and not any(flash_strip(1)[3::4])
    peak = flash_strip(0.5)
    assert max(flash_field(0.5)[3::4]) <= 153 and peak[128 * 4 + 1] > 235


@pytest.mark.parametrize("ratio", list(RESOLUTIONS))
def test_flash_overlay_all_ratios_and_layers(tmp_path, ratio):
    p = plan()
    s = p["segments"][0]
    w, h = RESOLUTIONS[ratio]
    w //= 6
    h //= 6
    flash = [{"frame": 300, "half": 6}]
    im = overlay_image(s, p["subtitle_style"], 300, w, h, tmp_path, flash, 300)
    assert 90 < im.getpixel((w // 2, h // 2))[3] <= 153
    # Explicit overlay stays above the warm flash.
    style = {
        **p["subtitle_style"],
        "x": 0.5,
        "y": 0.5,
        "color": "#0000FF",
        "outline": 0,
        "size": 120,
    }
    s["overlays"] = [
        {
            "id": "o",
            "kind": "text",
            "start": 0,
            "end": 360,
            "text": "TEST",
            "layer": 1,
            "style": style,
        }
    ]
    im = overlay_image(s, p["subtitle_style"], 300, w, h, tmp_path, flash, 300)
    assert any(b > r + 100 for r, g, b, a in im.get_flattened_data())


@pytest.fixture
def media(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    asset = tmp_path / "asset"
    asset.mkdir()
    for dest, color in [(source, "black"), (asset / "source.media", "blue")]:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color={color}:s=160x90:r=30:d=12",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                "12",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-c:a",
                "aac",
                "-f",
                "mp4",
                str(dest),
            ],
            check=True,
        )
    (asset / "metadata.json").write_text(json.dumps({"frames": 360}))
    monkeypatch.setattr("app.mix_render.folder", lambda _: asset)
    return source, tmp_path


def test_real_export_center_sound_and_flash(media):
    source, root = media
    p = plan()
    out = root / "flash.mp4"
    render_v2(source, p, out, preview=True, ratio="4:3")
    meta = probe(out)
    assert abs(float(meta["format"]["duration"]) - 12) < 1 / 30
    decoded = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(out),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-f",
            "f32le",
            "-",
        ]
    )
    y = np.frombuffer(decoded, dtype="<f4")
    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(ASSETS / "camera_shutter.wav"),
            "-ac",
            "1",
            "-f",
            "f32le",
            "-",
        ]
    )
    x = np.frombuffer(raw, dtype="<f4")
    start = sound_windows(p)[0]["start"]
    section = y[start - 100 : start + len(x) + 100]
    scores = np.correlate(section, x, "valid")
    lag = int(np.argmax(scores)) - 100
    assert abs(lag) <= 1
    assert np.sqrt(np.mean(y[: start - 500] ** 2)) < 0.0001
    pix = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(out),
            "-vf",
            "select=eq(n\\,300),scale=1:1",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
    )
    assert pix[0] > 60 and pix[1] > 50


def test_continuous_split_preserves_flash_duration():
    p = plan()
    items, d = global_items(p)
    expected = flashes(items, d)
    b = items[0]
    c = deepcopy(b)
    c.update(id="c", start=302, source_in=2, transition_in={"kind": "none", "sound": "none"})
    b = deepcopy(b)
    b.update(end=302, transition_out={"kind": "none", "sound": "none"})
    assert flashes([b, c], d) == expected
