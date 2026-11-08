from copy import deepcopy
from uuid import uuid4
import subprocess, json
import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError
from app.timeline import EditPlanV2
from app.visual_filters import sharpen_image, strength_at, intervals, ffmpeg_filters
from app.render_v2 import render_v2
from app.media import probe


def plan():
    return EditPlanV2(segments=[{"id": "s", "source_in": 0, "duration": 60}]).model_dump()


def f(**kwargs):
    return dict(
        id="filter",
        kind="sharpen",
        start=15,
        end=45,
        strength=25,
        targets=["image", "podcast", "broll"],
        **kwargs,
    )


def test_legacy_defaults_and_validation():
    p = plan()
    assert p["filters"] == []
    valid = f()
    p["filters"] = [valid]
    assert EditPlanV2.model_validate(p).filters[0].strength == 25
    for patch in [
        {"start": 45},
        {"end": 61},
        {"strength": 101},
        {"targets": ["image", "image"]},
        {"targets": ["text"]},
        {"kind": "unknown"},
    ]:
        p["filters"] = [{**valid, **patch}]
        with pytest.raises(ValidationError):
            EditPlanV2.model_validate(p)
    p["filters"] = [valid, valid]
    with pytest.raises(ValidationError):
        EditPlanV2.model_validate(p)
    p["filters"] = [{**valid, "targets": []}]
    assert EditPlanV2.model_validate(p)


def test_max_per_target_and_interval_boundaries():
    filters = [
        f(),
        {**f(), "id": "b", "start": 30, "end": 60, "strength": 80, "targets": ["broll"]},
    ]
    assert intervals(filters, "broll") == [(15, 30, 25), (30, 60, 80)]
    assert intervals(filters, "podcast") == [(15, 45, 25)]
    assert strength_at(filters, "image", 45) == 0
    assert strength_at(filters, "broll", 30) == 80
    assert ffmpeg_filters([{**f(), "strength": 0}], "image") == ""


@pytest.mark.parametrize("strength", [0, 25, 100])
def test_rgb_kernel_matches_ffmpeg(strength):
    rng = np.random.default_rng(8)
    arr = rng.integers(50, 200, (12, 16, 3), dtype=np.uint8)
    rgba = np.dstack([arr, np.full((12, 16), 255, dtype=np.uint8)])
    expected = np.asarray(sharpen_image(Image.fromarray(rgba), strength))[:, :, :3]
    chain = (
        ffmpeg_filters([{**f(), "start": 0, "end": 1, "strength": strength}], "podcast") or "null"
    )
    out = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "16x12",
            "-i",
            "-",
            "-vf",
            chain,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        input=arr.tobytes(),
    )
    actual = np.frombuffer(out, dtype=np.uint8).reshape(arr.shape)
    assert np.max(np.abs(actual[1:-1, 1:-1].astype(int) - expected[1:-1, 1:-1])) <= 1


def test_alpha_has_no_black_fringe():
    arr = np.zeros((8, 8, 4), dtype=np.uint8)
    arr[2:6, 2:6] = [180, 90, 40, 255]
    image = Image.fromarray(arr)
    out = np.asarray(sharpen_image(image, 100))
    assert np.array_equal(out[:, :, 3], arr[:, :, 3])
    assert np.array_equal(out[2:6, 2:6, :3], arr[2:6, 2:6, :3])
    assert sharpen_image(image, 0) is image


@pytest.mark.parametrize("target", ["podcast", "broll", "image"])
def test_real_render_selected_targets(tmp_path, monkeypatch, target):
    # Small isolated composition, so encoding assertions don't require a live database or worker.
    monkeypatch.setitem(
        __import__("app.timeline", fromlist=["RESOLUTIONS"]).RESOLUTIONS, "4:3", (160, 120)
    )
    source = tmp_path / "source.mp4"
    asset = tmp_path / "asset"
    asset.mkdir()
    for p in [source, asset / "source.media"]:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=160x120:r=30:d=2",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                "2",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-c:a",
                "aac",
                "-f",
                "mp4",
                str(p),
            ],
            check=True,
        )
    (asset / "metadata.json").write_text(json.dumps({"frames": 60}))
    monkeypatch.setattr("app.mix_render.folder", lambda _: asset)
    p = plan()
    p["filters"] = [{**f(), "targets": [target], "strength": 100}]
    if target == "broll":
        p["segments"][0]["broll"] = [
            {
                "id": "b",
                "asset_id": str(uuid4()),
                "start": 0,
                "end": 60,
                "source_in": 0,
                "transition_in": {"kind": "none", "frames": 0},
                "transition_out": {"kind": "none", "frames": 0},
            }
        ]
    if target == "image":
        folder = tmp_path / "assets"
        folder.mkdir()
        aid = str(uuid4())
        im = Image.new("RGBA", (32, 32), (200, 100, 40, 255))
        im.save(folder / (aid + ".png"))
        p["segments"][0]["overlays"] = [
            {"id": "i", "kind": "image", "asset_id": aid, "start": 0, "end": 60}
        ]
    for preview in [False, True]:
        out = tmp_path / f"{target}-{preview}.mp4"
        render_v2(source, p, out, preview=preview, ratio="4:3")
        meta = probe(out)
        v = next(s for s in meta["streams"] if s["codec_type"] == "video")
        assert int(v["nb_frames"]) == 60 and abs(float(meta["format"]["duration"]) - 2) < 1 / 30
        assert (v["width"], v["height"]) == ((54, 40) if preview else (160, 120))
