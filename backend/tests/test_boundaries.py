from copy import deepcopy
from uuid import uuid4
import subprocess, json
import numpy as np
import pytest
from app.timeline import EditPlanV2, RESOLUTIONS
from app.boundaries import normalize, boundaries, spans, events, validate_minimum
from app.render_v2 import render_v2
from app.media import probe


def plan():
    return EditPlanV2(
        segments=[dict(id="a", source_in=0, duration=60), dict(id="b", source_in=90, duration=60)]
    ).model_dump()


def test_boundary_identity_and_minimum():
    p = normalize(plan())
    e = boundaries(p)[1]
    assert e["frame"] == 60 and e["id"] == "p:a|p:b"
    p["transitions"][1]["value"] = {"kind": "flash", "frames": 12, "sound": "camera_shutter"}
    assert normalize(p) == p
    p["segments"][0]["duration"] = 90
    assert boundaries(p)[1]["frame"] == 90
    p["segments"].reverse()
    assert all(e["value"]["kind"] == "none" for e in boundaries(p))
    q = plan()
    q["segments"][0]["duration"] = 29
    with pytest.raises(ValueError):
        validate_minimum(q)
    validate_minimum(q, q)
    q2 = deepcopy(q)
    q2["segments"][0]["duration"] = 28
    with pytest.raises(ValueError):
        validate_minimum(q2, q)
    q2["segments"][0]["duration"] = 30
    validate_minimum(q2, q)


def test_legacy_broll_continuity_and_priority():
    p = plan()
    aid = str(uuid4())
    for i, s in enumerate(p["segments"]):
        s["broll"] = [
            dict(
                id="x" + str(i),
                asset_id=aid,
                start=0,
                end=60,
                source_in=60 * i,
                transform=s["transform"],
                transition_in={"kind": "black" if i == 0 else "none", "frames": 9},
                transition_out={"kind": "flash" if i == 1 else "none", "frames": 12},
            )
        ]
    p = normalize(p)
    assert len(spans(p)) == 1
    assert [e["value"]["kind"] for e in boundaries(p)] == ["black", "flash"]
    assert EditPlanV2.model_validate(p)
    assert all(e["half"] == 0 for e in events(p))


@pytest.mark.parametrize("kind", ["none", "black", "crossfade", "flash"])
def test_real_podcast_cut_render(tmp_path, monkeypatch, kind):
    monkeypatch.setitem(RESOLUTIONS, "4:3", (160, 120))
    src = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=160x120:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=160x120:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
    )
    p = normalize(plan())
    p["segments"][0]["source_in"] = 15
    p["segments"][1]["source_in"] = 120
    p["transitions"][1]["value"] = {
        "kind": kind,
        "frames": 12,
        "sound": "camera_shutter",
        "sound_volume": 0.4,
    }
    out = tmp_path / "out.mp4"
    render_v2(src, p, out, ratio="4:3")
    meta = probe(out)
    v = next(s for s in meta["streams"] if s["codec_type"] == "video")
    assert int(v["nb_frames"]) == 120
    assert abs(float(meta["format"]["duration"]) - 4) < 1 / 30
    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(out),
            "-vf",
            r"select=eq(n\,60)",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-threads",
            "1",
            "-",
        ]
    )
    pixel = np.frombuffer(raw, dtype=np.uint8).reshape(120, 160, 3)[60, 80]
    if kind == "black":
        assert pixel.max() < 12
    if kind == "crossfade":
        assert pixel[0] > 90 and pixel[2] > 90
    if kind == "none":
        assert pixel[2] > 220 and pixel[0] < 15
    from app.transition_effects import sound_windows

    event = sound_windows(p)[0]
    assert abs(event["start"] + event["length"] / 2 - 96000) <= 0.5


def test_image_replacement_spans_and_crossfade_use_still_frame():
    p = plan()
    image_id = str(uuid4())
    p["segments"][0]["image_asset_id"] = image_id
    p["segments"][0]["image_transform"] = {"mode": "fit", "x": 0.5, "y": 0.5, "scale": 1, "b": 0.5}
    broll_id = str(uuid4())
    p["segments"][0]["broll"] = [
        {
            "id": "still-broll",
            "asset_id": broll_id,
            "image_asset_id": image_id,
            "image_transform": {"mode": "fit", "x": 0.5, "y": 0.5, "scale": 1, "b": 0.5},
            "start": 30,
            "end": 60,
            "source_in": 140,
            "transform": {"mode": "fill", "x": 0.5, "y": 0.5, "scale": 1, "b": 0.7},
            "transition_in": {"kind": "crossfade", "frames": 12},
            "transition_out": {"kind": "none", "frames": 0},
        }
    ]
    p = EditPlanV2.model_validate(p).model_dump()
    p = normalize(p)
    assert spans(p)[0]["image_asset_id"] == image_id
    still = next(x for x in spans(p) if x["kind"] == "broll")
    assert still["image_asset_id"] == image_id and still["transform"]["mode"] == "fit"
    edge = next(x for x in events(p, {"podcast": 1, broll_id: 1}) if x["id"] == "p:a|b:still-broll")
    assert edge["kind"] == "crossfade" and not edge["fallback"]


def test_render_main_image_replacement_keeps_audio_and_fits_frame(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setitem(RESOLUTIONS, "4:3", (160, 120))
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=160x120:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    asset_id = str(uuid4())
    replacements = tmp_path / "replacement-images"
    replacements.mkdir()
    Image.new("RGB", (80, 120), (0, 0, 255)).save(replacements / f"{asset_id}.png")
    p = plan()
    p["segments"] = [p["segments"][0]]
    p = normalize(p)
    p["segments"][0].update(
        source_in=0,
        duration=60,
        image_asset_id=asset_id,
        image_transform={"mode": "fit", "x": 0.5, "y": 0.5, "scale": 1, "b": 0.5},
    )
    out = tmp_path / "still.mp4"
    render_v2(source, p, out, ratio="4:3")
    metadata = probe(out)
    assert any(stream["codec_type"] == "audio" for stream in metadata["streams"])
    frame = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(out),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-threads",
            "1",
            "-",
        ]
    )
    pixels = np.frombuffer(frame, dtype=np.uint8).reshape(120, 160, 3)
    assert pixels[60, 80, 2] > 220 and pixels[60, 80, 0] < 20
    assert pixels[60, 10].max() < 20


def test_render_broll_image_replacement_keeps_timing(tmp_path, monkeypatch):
    from PIL import Image
    from app import mix_render

    monkeypatch.setitem(RESOLUTIONS, "4:3", (160, 120))
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=160x120:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=3",
            "-shortest",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    library_id, image_id = str(uuid4()), str(uuid4())
    library_folder = tmp_path / "library"
    library_folder.mkdir()
    (library_folder / "metadata.json").write_text(json.dumps({"frames": 90}))
    monkeypatch.setattr(mix_render, "folder", lambda _asset_id: library_folder)
    replacements = tmp_path / "replacement-images"
    replacements.mkdir()
    Image.new("RGB", (160, 120), (0, 0, 255)).save(replacements / f"{image_id}.png")
    p = plan()
    p["segments"] = [p["segments"][0]]
    p["segments"][0].update(source_in=0, duration=90)
    p["segments"][0]["broll"] = [
        {
            "id": "image-slot",
            "asset_id": library_id,
            "image_asset_id": image_id,
            "image_transform": {"mode": "fit", "x": 0.5, "y": 0.5, "scale": 1, "b": 0.5},
            "start": 30,
            "end": 60,
            "source_in": 0,
            "reason": "test",
            "transform": {"mode": "fill", "x": 0.5, "y": 0.5, "scale": 1, "b": 0.7},
            "transition_in": {"kind": "none", "frames": 0},
            "transition_out": {"kind": "none", "frames": 0},
        }
    ]
    p = normalize(EditPlanV2.model_validate(p).model_dump())
    out = tmp_path / "broll-image.mp4"
    render_v2(source, p, out, ratio="4:3")
    metadata = probe(out)
    assert any(stream["codec_type"] == "audio" for stream in metadata["streams"])
    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            "1.5",
            "-i",
            str(out),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-threads",
            "1",
            "-",
        ]
    )
    pixel = np.frombuffer(raw, dtype=np.uint8).reshape(120, 160, 3)[60, 80]
    assert pixel[2] > 220 and pixel[0] < 20
    assert (
        int(
            next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")[
                "nb_frames"
            ]
        )
        == 90
    )


def test_crossfade_fallback():
    p = normalize(plan())
    p["transitions"][1]["value"] = {"kind": "crossfade", "frames": 12}
    p["segments"][1]["source_in"] = 0
    event = events(p, {"podcast": 150})[1]
    assert event["fallback"] and event["kind"] == "black"
