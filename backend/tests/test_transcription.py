import importlib.util, json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app import transcription as t
from app.media import Cancelled


def test_ranges_and_overlap_word_ownership_keep_repetitions():
    parts = list(t.ranges(241))
    assert len(parts) == 3
    assert parts[1] == {"index": 1, "start": 120, "end": 240, "input_start": 118, "input_end": 241}
    words = [
        {"start": 1.5, "end": 2.3, "text": "batas"},
        {"start": 3, "end": 3.2, "text": "ya"},
        {"start": 3.3, "end": 3.5, "text": "ya"},
    ]
    absolute = t.absolute_words(words, parts[1], 241)
    assert [w["text"] for w in absolute] == ["ya", "ya"]
    assert [w["text"] for w in t.merge_words([absolute, [dict(absolute[0])]])] == ["ya", "ya"]
    assert len(t.merge_words([[absolute[0], dict(absolute[0])]])) == 2


class FakeChild:
    calls = []

    def __init__(self, *_):
        self.peak = 400 * 1024**2

    def wait(self, *_):
        return {"event": "ready"}

    def transcribe(self, audio, index, language):
        self.calls.append((index, language))
        return {
            "words": [{"start": 10, "end": 10.5, "text": "test"}],
            "language": "id",
            "index": index,
        }

    def close(self):
        pass


@pytest.fixture
def audio(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test media")
    FakeChild.calls = []
    monkeypatch.setattr(t, "Child", FakeChild)
    monkeypatch.setattr(t, "run", lambda args, _check: Path(args[-1]).write_bytes(b"audio"))
    return source


def test_chunk_checkpoint_resume_language_and_legacy_transcript(audio):
    def stop_after_one(**kw):
        if kw.get("metrics", {}).get("processed_seconds") == 120:
            raise Cancelled()

    with pytest.raises(Cancelled):
        t.transcribe("job", audio, 241, lambda: None, stop_after_one)
    assert [c[0] for c in FakeChild.calls] == [0]
    result = t.transcribe("job", audio, 241, lambda: None, lambda **_: None)
    assert [c[0] for c in FakeChild.calls] == [0, 1, 2]
    assert FakeChild.calls[1][1] == "id"
    assert [w["start"] for w in result["words"]] == [10, 128]
    assert result["transcription"]["chunks"] == 3
    audio.unlink()
    assert t.transcribe("job", audio, 241, lambda: None, lambda **_: None) == result


def test_memory_failures_are_bounded_and_manual_retry_keeps_chunks(audio, monkeypatch):
    class Failing(FakeChild):
        attempts = 0

        def wait(self, *_):
            Failing.attempts += 1
            raise t.TranscriptionFailure("RAM")

    monkeypatch.setattr(t, "Child", Failing)
    with pytest.raises(t.TranscriptionFailure):
        t.transcribe("job", audio, 120, lambda: None, lambda **_: None)
    assert Failing.attempts == 2
    with pytest.raises(t.TranscriptionFailure):
        t.transcribe("job", audio, 120, lambda: None, lambda **_: None)
    assert Failing.attempts == 2
    t.allow_manual_retry(audio.parent)
    monkeypatch.setattr(t, "Child", FakeChild)
    assert t.transcribe("job", audio, 120, lambda: None, lambda **_: None)["words"]


def test_memory_supervisor_terminates_before_reading_large_response(monkeypatch):
    child = t.Child.__new__(t.Child)
    child.limit = 100
    child.proc = SimpleNamespace(pid=1)
    child.peak = 0
    child.check = lambda: None
    child.last_check = 0
    monkeypatch.setattr(t, "process_rss", lambda _: 101)
    with pytest.raises(t.TranscriptionFailure, match="Memori"):
        child.wait("result")


def test_worker_restart_budget():
    path = Path(__file__).resolve().parents[2] / "scripts/worker_supervisor.py"
    spec = importlib.util.spec_from_file_location("worker_supervisor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policy = module.RestartPolicy()
    assert [policy.delay(n) for n in [0, 10, 20, 30]] == [5, 15, 30, None]
    assert policy.delay(650) == 5


def test_database_interruption_refunds_only_incomplete_attempt(audio, monkeypatch):
    from sqlalchemy.exc import OperationalError

    class Interrupted(FakeChild):
        def transcribe(self, *_):
            raise OperationalError("select", {}, Exception("network unavailable"))

    monkeypatch.setattr(t, "Child", Interrupted)
    with pytest.raises(OperationalError):
        t.transcribe("job", audio, 120, lambda: None, lambda **_: None)
    manifest = next((audio.parent / "transcription").glob("*/manifest.json"))
    assert json.loads(manifest.read_text())["attempts"]["0"] == 0
    monkeypatch.setattr(t, "Child", FakeChild)
    assert t.transcribe("job", audio, 120, lambda: None, lambda **_: None)["words"]


def test_database_error_before_child_start_does_not_spend_attempt(audio):
    from sqlalchemy.exc import OperationalError

    def unavailable(**kw):
        if kw.get("stage"):
            raise OperationalError("update", {}, Exception("database offline"))

    with pytest.raises(OperationalError):
        t.transcribe("job", audio, 120, lambda: None, unavailable)
    state = json.loads(next((audio.parent / "transcription").glob("*/manifest.json")).read_text())
    assert state["attempts"]["0"] == 0
    assert FakeChild.calls == []


def test_source_identity_cache_invalidates_when_source_changes(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"first source")
    first = t.source_identity(source)
    import hashlib

    factory = hashlib.sha256
    calls = []

    def digest(*args):
        calls.append(True)
        return factory(*args)

    monkeypatch.setattr(t.hashlib, "sha256", digest)
    assert t.source_identity(source) == first and not calls
    source.write_bytes(b"changed source with different size")
    assert t.source_identity(source) != first and calls


def test_profile_switch_does_not_mix_unfinished_chunks(audio, monkeypatch):
    monkeypatch.setattr(
        t,
        "settings",
        SimpleNamespace(whisper_model="small", whisper_profile="standard", whisper_threads=2),
    )

    def interrupt_after_first(**kw):
        if kw.get("metrics", {}).get("processed_seconds") == 120:
            raise Cancelled()

    with pytest.raises(Cancelled):
        t.transcribe("trial", audio, 241, lambda: None, interrupt_after_first)
    assert [index for index, _ in FakeChild.calls] == [0]
    monkeypatch.setattr(
        t,
        "settings",
        SimpleNamespace(whisper_model="base", whisper_profile="light", whisper_threads=2),
    )
    result = t.transcribe("trial", audio, 241, lambda: None, lambda **_: None)
    assert [index for index, _ in FakeChild.calls] == [0, 0, 1, 2]
    assert result["transcription"]["model"] == "base"
    assert result["transcription"]["profile"] == "light"
    manifests = list((audio.parent / "transcription").glob("*/manifest.json"))
    assert len(manifests) == 2
    monkeypatch.setattr(
        t,
        "settings",
        SimpleNamespace(whisper_model="small", whisper_profile="standard", whisper_threads=2),
    )
    assert t.transcribe("trial", audio, 241, lambda: None, lambda **_: None) == result
