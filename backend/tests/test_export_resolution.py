from pathlib import Path
import subprocess
import pytest
from pydantic import ValidationError
from app.export_options import ExportRequest, dimensions, render_identity
from app.timeline import EditPlanV2
from app.render_v2 import render_v2
from app.media import probe


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    folder = tmp_path_factory.mktemp("resolutions")
    path = folder / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.mark.parametrize("ratio", ["9:16", "16:9", "1:1", "4:5", "4:3"])
@pytest.mark.parametrize("resolution", [360, 720, 1080])
def test_real_export_dimensions(source, tmp_path, ratio, resolution):
    plan = EditPlanV2(segments=[dict(id="a", source_in=0, duration=3)]).model_dump()
    out = tmp_path / "out.mp4"
    render_v2(source, plan, out, ratio=ratio, resolution=resolution)
    data = probe(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == dimensions(ratio, resolution)
    assert int(video["nb_frames"]) == 3
    assert any(s["codec_type"] == "audio" for s in data["streams"])


def test_request_and_checkpoint_identity(tmp_path):
    assert ExportRequest().resolution == 1080
    for value in [240, 2160]:
        with pytest.raises(ValidationError):
            ExportRequest(resolution=value)
    with pytest.raises(ValidationError):
        ExportRequest(path="/tmp", width=100)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"one")
    p = {"segments": []}
    first = render_identity(source, p, "4:3", 360)
    assert first != render_identity(source, p, "4:3", 720)
    source.write_bytes(b"another")
    assert first != render_identity(source, p, "4:3", 360)
