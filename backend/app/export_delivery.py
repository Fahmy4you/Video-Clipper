"""Developer-controlled export delivery. No destination is accepted from HTTP clients."""

import os, re, shutil, subprocess, tempfile, unicodedata
from pathlib import Path
from pydantic import BaseModel
from .config import settings


class ExportDeliveryError(ValueError, RuntimeError):
    pass


class ExportConfigView(BaseModel):
    mode: str
    local_dir: str | None = None
    ready: bool
    error: str | None = None


def destination_path(value):
    if re.match(r"^[A-Za-z]:[/\\]", value):
        if os.name == "nt":
            return Path(value)
        if "microsoft" not in Path("/proc/sys/kernel/osrelease").read_text().lower():
            raise ExportDeliveryError("Path Windows hanya dapat digunakan pada Windows atau WSL.")
        return Path(subprocess.check_output(["wslpath", "-u", value], text=True).strip())
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ExportDeliveryError("Folder ekspor harus memakai path absolut.")
    return path


def validate(config):
    mode = config.get("mode") or "global"
    if mode not in ("global", "local"):
        raise ExportDeliveryError("EXPORT_MODE harus global atau local.")
    if mode == "global":
        return None
    value = config.get("local_dir", "").strip()
    if not value:
        raise ExportDeliveryError("Isi EXPORT_LOCAL_DIR untuk ekspor local.")
    path = destination_path(value)
    if not path.is_dir():
        raise ExportDeliveryError("Folder ekspor tidak ditemukan: " + value)
    try:
        with tempfile.NamedTemporaryFile(prefix=".video-clipping-check-", dir=path):
            pass
    except OSError as e:
        raise ExportDeliveryError("Folder ekspor tidak dapat ditulis: " + value) from e
    return path


def config_snapshot():
    config = {
        "mode": settings.export_mode.strip().lower() or "global",
        "local_dir": settings.export_local_dir.strip(),
    }
    validate(config)
    return config


def config_view():
    config = {
        "mode": settings.export_mode.strip().lower() or "global",
        "local_dir": settings.export_local_dir.strip(),
    }
    try:
        validate(config)
        error = None
    except (ValueError, OSError) as e:
        error = str(e)
    return {
        **config,
        "local_dir": config["local_dir"] or None,
        "ready": error is None,
        "error": error,
    }


def filename(title, revision, job_id, resolution=None):
    text = unicodedata.normalize("NFKC", title)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", text).strip(" .")[:100] or "highlight"
    text = text.encode("utf-8")[:120].decode("utf-8", "ignore").rstrip(" .") or "highlight"
    quality = f"-{resolution}p" if resolution else ""
    return f"{text}{quality}-r{revision}-{job_id}.mp4"


def display_path(config, path, name):
    value = config.get("local_dir", "")
    return (
        value.rstrip("/\\") + "/" + name
        if re.match(r"^[A-Za-z]:[/\\]", value)
        else str(path / name)
    )


def deliver(source, config, name, check=lambda: None):
    path = validate(config)
    if path is None:
        return {"export_mode": "global", "delivery_status": "ready", "filename": name}
    target = path / name
    if target.exists():
        # Never overwrite an existing destination, including on a retried job.
        if target.stat().st_size == source.stat().st_size:
            import hashlib

            def digest(p):
                h = hashlib.sha256()
                with p.open("rb") as f:
                    for block in iter(lambda: f.read(1024 * 1024), b""):
                        check()
                        h.update(block)
                return h.digest()

            if digest(target) == digest(source):
                return {
                    "export_mode": "local",
                    "delivery_status": "saved",
                    "filename": name,
                    "local_path": display_path(config, path, name),
                }
        raise ExportDeliveryError("Nama file tujuan sudah dipakai; file yang ada tidak ditimpa.")
    fd, tmp = tempfile.mkstemp(prefix=".video-clipping-", suffix=".part", dir=path)
    try:
        with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
            while block := src.read(1024 * 1024):
                check()
                dst.write(block)
            dst.flush()
            os.fsync(dst.fileno())
        check()
        validate(config)
        # Atomic publication without replacing a pre-existing file.
        os.link(tmp, target)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {
        "export_mode": "local",
        "delivery_status": "saved",
        "filename": name,
        "local_path": display_path(config, path, name),
    }
