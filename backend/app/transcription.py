"""Checkpointed two-minute transcription with bounded memory and child supervision."""

import hashlib, json, math, os, select, signal, subprocess, sys, tempfile, time
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from .config import settings
from .media import run, write_json, Cancelled
from .job_diagnostics import event, memory_limit, process_rss

CORE = 120
CONTEXT = 2
VERSION = 1


class TranscriptionFailure(RuntimeError):
    pass


def ranges(duration):
    for index in range(math.ceil(duration / CORE)):
        start = index * CORE
        end = min(duration, start + CORE)
        yield {
            "index": index,
            "start": start,
            "end": end,
            "input_start": max(0, start - CONTEXT),
            "input_end": min(duration, end + CONTEXT),
        }


def release_source_cache(source):
    # This private source can exceed a gigabyte. Reclaim its clean page cache so
    # Windows is not starved by WSL retaining a full-file verification read.
    try:
        with source.open("rb") as stream:
            os.posix_fadvise(stream.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    except (OSError, AttributeError):
        pass


def source_identity(source):
    stat = source.stat()
    identity = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    cache = source.parent / "source-identity.json"
    try:
        saved = json.loads(cache.read_text())
        if saved.get("stat") == identity and len(saved.get("sha256", "")) == 64:
            return saved["sha256"]
    except (OSError, ValueError, TypeError):
        pass
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        offset = 0
        for block in iter(lambda: stream.read(4 * 1024**2), b""):
            digest.update(block)
            try:
                os.posix_fadvise(stream.fileno(), offset, len(block), os.POSIX_FADV_DONTNEED)
            except (OSError, AttributeError):
                pass
            offset += len(block)
    release_source_cache(source)
    value = digest.hexdigest()
    write_json(cache, {"stat": identity, "sha256": value})
    return value


def absolute_words(words, part, duration):
    result = []
    for word in words:
        start = float(word["start"]) + part["input_start"]
        end = float(word["end"]) + part["input_start"]
        text = str(word["text"]).strip()
        if not math.isfinite(start + end) or end <= start or not text:
            continue
        midpoint = (start + end) / 2
        if not part["start"] <= midpoint < part["end"]:
            continue
        result.append(
            {"start": round(max(0, start), 4), "end": round(min(duration, end), 4), "text": text}
        )
    return result


def merge_words(parts):
    result = []
    origins = []
    indexed = ((index, word) for index, part in enumerate(parts) for word in part)
    for origin, word in sorted(indexed, key=lambda item: (item[1]["start"], item[1]["end"])):
        # Deduplication is only for overlap between chunks; retain repetitions
        # emitted within one chunk even if the model aligned their times alike.
        if result and origins[-1] != origin:
            prev = result[-1]
            intersection = max(0, min(prev["end"], word["end"]) - max(prev["start"], word["start"]))
            overlap = intersection / min(prev["end"] - prev["start"], word["end"] - word["start"])
            if prev["text"].casefold() == word["text"].casefold() and overlap > 0.8:
                continue
        result.append(word)
        origins.append(origin)
    return result


class Child:
    def __init__(self, check, on_metrics, jid, model=None):
        self.check = check
        self.on_metrics = on_metrics
        self.jid = jid
        self.peak = 0
        self.buffer = b""
        self.pending = []
        self.limit = memory_limit()
        self.log = tempfile.TemporaryFile()
        fd = os.environ.get("VC_HEAVY_LOCK_FD")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.transcription_child"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            start_new_session=True,
            env={
                **os.environ,
                "HF_HUB_DISABLE_XET": "1",
                "VC_PARENT_PID": str(os.getpid()),
                "VC_WHISPER_MODEL": model or settings.whisper_model,
                "OMP_NUM_THREADS": str(settings.whisper_threads),
                "OPENBLAS_NUM_THREADS": str(settings.whisper_threads),
                "MKL_NUM_THREADS": str(settings.whisper_threads),
            },
            pass_fds=(int(fd),) if fd else (),
        )
        self.last_report = 0
        self.last_check = 0

    def wait(self, wanted):
        deadline = time.monotonic() + 900
        while True:
            if time.monotonic() - self.last_check >= 1:
                self.check()
                self.last_check = time.monotonic()
            rss = process_rss(self.proc.pid)
            self.peak = max(self.peak, rss)
            if rss > self.limit:
                raise TranscriptionFailure(
                    "Memori transkripsi melewati batas aman. Bagian tersimpan tetap tersedia; hentikan aplikasi berat lain lalu coba lagi."
                )
            if time.monotonic() - self.last_report > 3:
                self.on_metrics(
                    {
                        "memory_bytes": rss,
                        "peak_memory_bytes": self.peak,
                        "memory_limit_bytes": self.limit,
                    }
                )
                self.last_report = time.monotonic()
            for item in list(self.pending):
                self.pending.remove(item)
                if item.get("event") == "error":
                    raise TranscriptionFailure(
                        "Proses transkripsi gagal ("
                        + item.get("type", "unknown")
                        + "). Checkpoint sebelumnya tetap tersedia."
                    )
                if item.get("event") == wanted:
                    return item
            if self.proc.poll() is not None:
                raise TranscriptionFailure(
                    "Proses transkripsi berhenti dengan exit code "
                    + str(self.proc.returncode)
                    + ". Checkpoint sebelumnya tetap tersedia."
                )
            if time.monotonic() > deadline:
                raise TranscriptionFailure(
                    "Satu bagian transkripsi tidak selesai dalam 15 menit. Checkpoint sebelumnya tetap tersedia."
                )
            readable, _, _ = select.select([self.proc.stdout], [], [], 0.25)
            if readable:
                data = os.read(self.proc.stdout.fileno(), 65536)
                if data:
                    self.buffer += data
                    while b"\n" in self.buffer:
                        line, self.buffer = self.buffer.split(b"\n", 1)
                        try:
                            self.pending.append(json.loads(line))
                        except ValueError:
                            pass

    def transcribe(self, audio, index, language, hotwords=None):
        self.proc.stdin.write(
            (
                json.dumps(
                    {
                        "audio": str(audio),
                        "index": index,
                        "language": language,
                        "hotwords": hotwords,
                    }
                )
                + "\n"
            ).encode()
        )
        self.proc.stdin.flush()
        response = self.wait("result")
        if response.get("index") != index:
            raise TranscriptionFailure("Respons bagian transkripsi tidak cocok.")
        return response

    def close(self):
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait()
        event(
            "transcription_child_exit",
            job_id=self.jid,
            exit_code=self.proc.returncode,
            peak_memory_bytes=self.peak,
            limit_bytes=self.limit,
        )
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.log.close()


def transcribe(jid, source, duration, check, update):
    folder = source.parent
    target = folder / "transcript.json"
    if target.exists():
        return json.loads(target.read_text())
    root = folder / "transcription"
    root.mkdir(exist_ok=True)
    check()
    identity = {
        "version": VERSION,
        "source": source_identity(source),
        "model": settings.whisper_model,
        "threads": settings.whisper_threads,
        "compute_type": "int8",
        "core": CORE,
        "context": CONTEXT,
        "word_timestamps": True,
        "vad_filter": True,
    }
    signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    chunks = root / signature
    chunks.mkdir(exist_ok=True)
    manifest = chunks / "manifest.json"
    try:
        state = json.loads(manifest.read_text())
    except (OSError, ValueError):
        state = {"identity": identity, "attempts": {}, "language": None}
    parts = list(ranges(duration))
    results = []
    child = None
    language = state.get("language")
    started = time.monotonic()
    new_completed = 0
    peak = 0
    try:
        for part in parts:
            check()
            path = chunks / (str(part["index"]).zfill(5) + ".json")
            saved = None
            try:
                candidate = json.loads(path.read_text())
                if candidate["part"] == part and candidate["signature"] == signature:
                    # Validate a checkpoint before treating it as completed.
                    from .schemas import Word

                    for word in candidate["words"]:
                        Word.model_validate(word)
                    saved = candidate
            except (OSError, ValueError, KeyError, TypeError):
                pass
            if saved:
                results.append(saved["words"])
                language = language or saved.get("language")
                update(
                    metrics={
                        "chunks_completed": part["index"] + 1,
                        "processed_seconds": part["end"],
                        "total_seconds": duration,
                        "chunks_total": len(parts),
                        "eta_seconds": None,
                    }
                )
                continue
            index = str(part["index"])
            attempts = state.setdefault("attempts", {}).get(index, 0)
            if attempts >= 2:
                raise TranscriptionFailure(
                    "Bagian "
                    + str(part["index"] + 1)
                    + " gagal dua kali. Bagian sebelumnya tersimpan; coba ulang manual setelah memeriksa sumber daya."
                )
            while attempts < 2:
                check()
                attempts += 1
                state["attempts"][index] = attempts
                write_json(manifest, state)
                try:
                    update(
                        stage="Transkripsi lokal",
                        progress=35 + int(39 * part["start"] / duration),
                        metrics={
                            "chunk_index": part["index"] + 1,
                            "chunks_total": len(parts),
                            "processed_seconds": part["start"],
                            "total_seconds": duration,
                            "chunk_attempt": attempts,
                        },
                    )
                    if child is None:
                        child = Child(check, lambda metrics: update(metrics=metrics), jid)
                        child.wait("ready")
                    audio = chunks / "current.wav"
                    run(
                        [
                            "ffmpeg",
                            "-y",
                            "-v",
                            "error",
                            "-ss",
                            str(part["input_start"]),
                            "-i",
                            str(source),
                            "-t",
                            str(part["input_end"] - part["input_start"]),
                            "-vn",
                            "-ac",
                            "1",
                            "-ar",
                            "16000",
                            str(audio),
                        ],
                        check,
                    )
                    release_source_cache(source)
                    response = child.transcribe(audio, part["index"], language)
                    peak = max(peak, child.peak)
                    words = absolute_words(response["words"], part, duration)
                    language = language or (response.get("language") if words else None)
                    write_json(
                        path,
                        {
                            "signature": signature,
                            "part": part,
                            "language": language,
                            "words": words,
                        },
                    )
                    state["language"] = language
                    write_json(manifest, state)
                    audio.unlink(missing_ok=True)
                    results.append(words)
                    new_completed += 1
                    elapsed = time.monotonic() - started
                    remaining = len(parts) - part["index"] - 1
                    update(
                        progress=35 + int(39 * part["end"] / duration),
                        metrics={
                            "chunks_completed": part["index"] + 1,
                            "processed_seconds": part["end"],
                            "eta_seconds": round(elapsed / new_completed * remaining)
                            if new_completed >= 2
                            else None,
                            "peak_memory_bytes": peak,
                        },
                    )
                    event(
                        "transcription_chunk_complete",
                        job_id=jid,
                        index=part["index"],
                        processed_seconds=part["end"],
                        total_seconds=duration,
                        peak_memory_bytes=peak,
                    )
                    break
                except (Cancelled, SQLAlchemyError):
                    # An orderly cancellation or DB interruption is not a model failure.
                    state["attempts"][index] = max(0, attempts - 1)
                    write_json(manifest, state)
                    raise
                except TranscriptionFailure:
                    if child:
                        peak = max(peak, child.peak)
                        child.close()
                        child = None
                    if attempts >= 2:
                        raise
                    event(
                        "transcription_chunk_retry",
                        job_id=jid,
                        index=part["index"],
                        attempt=attempts,
                    )
        result = {
            "language": language,
            "words": merge_words(results),
            "transcription": {
                "signature": signature,
                "profile": settings.whisper_profile,
                "model": settings.whisper_model,
                "device": "cpu",
                "compute_type": "int8",
                "threads": settings.whisper_threads,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "chunks": len(parts),
                "peak_memory_bytes": peak,
            },
        }
        check()
        write_json(target, result)
        return result
    finally:
        if child:
            child.close()


def allow_manual_retry(folder):
    # A deliberate retry is a new bounded attempt cycle; successful chunks stay intact.
    root = folder / "transcription"
    if not root.exists():
        return
    for path in root.glob("*/manifest.json"):
        try:
            value = json.loads(path.read_text())
            value["attempts"] = {}
            write_json(path, value)
        except (OSError, ValueError):
            pass
