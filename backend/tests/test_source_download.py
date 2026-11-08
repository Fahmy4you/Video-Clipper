from pathlib import Path
from types import SimpleNamespace
import pytest
import yt_dlp
from app import source_cache


def fake_download(monkeypatch, tmp_path, error=None):
    captured = {}

    class Fake:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, *args, **kwargs):
            return {"id": "niXAuUhK-tw", "duration": 120, "title": "Source", "format_id": "140"}

        def process_ie_result(self, info, download):
            if error:
                raise yt_dlp.utils.DownloadError(error)
            p = tmp_path / "audio.140.webm"
            p.write_bytes(b"download")
            return {"requested_downloads": [{"filepath": str(p)}]}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Fake)
    monkeypatch.setattr(source_cache, "inspect", lambda *args: 120)
    monkeypatch.setattr(source_cache, "probe", lambda *args: {"streams": [{"codec_type": "audio"}]})
    monkeypatch.setattr(
        source_cache, "run", lambda args, check: Path(args[-1]).write_bytes(b"complete")
    )
    return captured


def test_audio_first_options_and_completion_marker(tmp_path, monkeypatch):
    captured = fake_download(monkeypatch, tmp_path)
    result = source_cache.download(tmp_path, "url", False, lambda: None, lambda **kw: None)
    assert result.name == "audio.m4a" and result.read_bytes() == b"complete"
    assert captured["format"] == "bestaudio/best"
    assert captured["continuedl"] and captured["retries"] == 5
    assert captured["socket_timeout"] == 60 and captured["skip_unavailable_fragments"] is False
    assert captured["concurrent_fragment_downloads"] == 1


def test_network_failure_preserves_partial(tmp_path, monkeypatch):
    fake_download(monkeypatch, tmp_path, "Connection timed out")
    partial = tmp_path / "audio.140.webm.part"
    partial.write_bytes(b"saved")
    with pytest.raises(source_cache.DownloadWait):
        source_cache.download(tmp_path, "url", False, lambda: None, lambda **kw: None)
    assert partial.read_bytes() == b"saved" and not (tmp_path / "audio.m4a").exists()


@pytest.mark.parametrize("reason", ["Private video", "Video unavailable", "Sign in to confirm"])
def test_permanent_source_failure_is_not_network_wait(tmp_path, monkeypatch, reason):
    fake_download(monkeypatch, tmp_path, reason)
    with pytest.raises(RuntimeError, match="autentikasi"):
        source_cache.download(tmp_path, "url", False, lambda: None, lambda **kw: None)


def test_complete_download_is_not_repeated(tmp_path, monkeypatch):
    captured = fake_download(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"complete")
    result = source_cache.download(tmp_path, "url", True, lambda: None, lambda **kw: None)
    assert result.name == "source.mp4" and not captured


def test_published_file_with_missing_marker_recovers_metadata(tmp_path, monkeypatch):
    captured = fake_download(monkeypatch, tmp_path)
    (tmp_path / "source.mp4").write_bytes(b"complete")
    (tmp_path / "video-download.json").write_text('{"title":"Recovered title"}')
    source_cache.download(tmp_path, "url", True, lambda: None, lambda **kw: None)
    import json

    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["title"] == "Recovered title" and metadata["duration"] == 120
    assert not captured
