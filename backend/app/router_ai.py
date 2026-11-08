"""9Router metadata and structured generation. Credentials are read for every request."""

import hashlib
import json
import os
import platform
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from fastapi import HTTPException

from .config import ROOT, STORAGE
from .media import write_json

ENV_PATH = ROOT / ".env"
_lock = threading.Lock()
_pending = set()


class ConfigError(RuntimeError):
    pass


class ContextLimit(RuntimeError):
    pass


class ProviderWait(Exception):
    def __init__(self, reason, kind="waiting_service", retry_after=None):
        self.reason = reason
        self.kind = kind
        self.retry_after = retry_after


@dataclass(frozen=True)
class RouterConfig:
    url: str
    key: str

    @property
    def identity(self):
        return hashlib.sha256((self.url + "\0" + self.key).encode()).hexdigest()[:24]


def configuration():
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    url = (
        str(values.get("9router_base_url", os.getenv("9router_base_url", "")) or "")
        .strip()
        .rstrip("/")
    )
    key = str(values.get("9router_key", os.getenv("9router_key", "")) or "").strip()
    parsed = urlsplit(url)
    if not url or not key:
        raise ConfigError(
            "Isi 9router_base_url dan 9router_key pada .env. Transkrip dan checkpoint tetap tersimpan."
        )
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(
            "9router_base_url harus berupa alamat HTTP/HTTPS tanpa kredensial atau parameter, diakhiri /v1."
        )
    if parsed.path.rstrip("/") != "/v1":
        raise ConfigError("9router_base_url harus diakhiri /v1.")
    return RouterConfig(url, key)


def redact(message):
    text = str(message)
    try:
        text = text.replace(configuration().key, "[redacted]")
    except ConfigError:
        pass
    return re.sub(r"(?i)(bearer\s+|[?&](?:key|token|api_key)=)[^\s&]+", r"\1[redacted]", text)


def client(config, timeout=15):
    return httpx.Client(
        headers={"Authorization": "Bearer " + config.key}, timeout=timeout, follow_redirects=False
    )


def connection_error(config):
    host = urlsplit(config.url).hostname
    is_wsl = "microsoft" in platform.release().lower() or bool(os.getenv("WSL_INTEROP"))
    if is_wsl and host in ("localhost", "127.0.0.1", "::1"):
        return (
            "9Router tidak dapat dijangkau dari WSL. localhost mengarah ke Ubuntu. "
            "Jika 9Router berjalan di Windows, gunakan alamat host Windows pada "
            "9router_base_url, diakhiri /v1. Lihat ip route show default."
        )
    return "9Router tidak dapat dijangkau. Periksa endpoint, layanan, dan akses jaringan."


def cache_path(config):
    return STORAGE / "router-catalog" / (config.identity + ".json")


def read_cache(config):
    try:
        data = json.loads(cache_path(config).read_text())
        return data if data.get("version") == 1 else {}
    except (OSError, ValueError, TypeError):
        return {}


def _error(response):
    status = response.status_code
    if status in (401, 403):
        return ConfigError("Key 9Router ditolak. Periksa key dan izin pada dashboard 9Router.")
    if status == 404:
        return RuntimeError(
            "Combo atau endpoint 9Router tidak ditemukan. Perbarui katalog dan pilih combo yang tersedia."
        )
    if status in (400, 413):
        try:
            code = str(response.json().get("error", {}).get("code", "")).lower()
        except (ValueError, AttributeError):
            code = ""
        if status == 413 or code in ("context_length_exceeded", "input_too_long"):
            return ContextLimit("Transkrip melebihi kapasitas konteks combo.")
    retry = response.headers.get("retry-after")
    try:
        delay = max(1, float(retry)) if retry else None
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            delay = max(1, parsedate_to_datetime(retry).timestamp() - time.time())
        except (TypeError, ValueError):
            delay = None
    if status == 429:
        return ProviderWait(
            "9Router membatasi permintaan (429). Jenis batas kuota tidak dapat dipastikan dari status ini.",
            "waiting_quota",
            delay,
        )
    if status >= 500 or status in (408, 409):
        return ProviderWait(
            "9Router atau penyedia sedang terganggu. Checkpoint tersimpan.", retry_after=delay
        )
    return RuntimeError(
        "Permintaan analisis ditolak 9Router (HTTP "
        + str(status)
        + "). Periksa format permintaan dan konfigurasi combo."
    )


def _refresh(config):
    path = cache_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A file lease combines refreshes across API/worker processes.
    import fcntl

    with path.with_suffix(".lock").open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            with _lock:
                _pending.discard(config.identity)
            return
        previous = read_cache(config)
        try:
            with client(config) as http:
                response = http.get(config.url + "/models")
            if response.status_code >= 400:
                raise _error(response)
            rows = response.json()["data"]
            if not isinstance(rows, list):
                raise ValueError("Invalid catalog")
            models = []
            for row in rows:
                if row.get("owned_by") != "combo":
                    continue
                name = row.get("id")
                if isinstance(name, str) and name and not any(x["id"] == name for x in models):
                    models.append(
                        {"id": name, "name": name, "context_length": row.get("context_length")}
                    )
            write_json(
                path, {"version": 1, "models": models, "fetched_at": time.time(), "error": None}
            )
        except Exception as error:
            attempts = int(previous.get("failures", 0)) + 1
            if isinstance(error, httpx.RequestError):
                message = connection_error(config)
            else:
                message = (
                    str(error)
                    if isinstance(error, (ConfigError, RuntimeError, ProviderWait))
                    else "Katalog 9Router belum dapat diakses. Periksa alamat dan koneksi layanan."
                )
            write_json(
                path,
                {
                    **previous,
                    "version": 1,
                    "error": redact(message),
                    "failures": attempts,
                    "next_attempt": time.time() + (60, 300, 900)[min(attempts - 1, 2)],
                },
            )
        finally:
            with _lock:
                _pending.discard(config.identity)


def schedule(connection=None, force=False):
    try:
        config = configuration()
    except ConfigError:
        return
    saved = read_cache(config)
    if not force and (
        saved.get("fetched_at", 0) > time.time() - 300 or saved.get("next_attempt", 0) > time.time()
    ):
        return
    with _lock:
        if config.identity in _pending:
            return
        _pending.add(config.identity)
    threading.Thread(target=_refresh, args=(config,), daemon=True).start()


def snapshot(update=True):
    try:
        config = configuration()
    except ConfigError as error:
        return {
            "models": [],
            "connections": [],
            "refreshing": False,
            "stale": True,
            "error": str(error),
        }
    saved = read_cache(config)
    if update:
        schedule()
    stale = saved.get("fetched_at", 0) < time.time() - 300
    refreshing = config.identity in _pending
    fetched = saved.get("fetched_at")
    stamp = datetime.fromtimestamp(fetched, timezone.utc).isoformat() if fetched else None
    models = [
        {**m, "status": "catalog", "selectable": True, "stale": stale, "connections": []}
        for m in saved.get("models", [])
    ]
    return {
        "models": models,
        "refreshing": refreshing,
        "stale": stale,
        "connections": [
            {
                "id": "9router",
                "label": "9Router",
                "refreshing": refreshing,
                "stale": stale,
                "fetched_at": stamp,
                "next_attempt_at": None,
                "error": saved.get("error"),
                "model_count": len(models),
            }
        ],
    }


def connection_status(catalog=None):
    catalog = snapshot() if catalog is None else catalog
    try:
        configuration()
    except ConfigError as error:
        return {
            "configured": False,
            "connected": False,
            "connection_status": "unconfigured",
            "error": str(error),
        }
    connection = next(iter(catalog.get("connections", [])), {})
    error = connection.get("error")
    connected = bool(connection.get("fetched_at")) and not error
    status = (
        "checking"
        if catalog.get("refreshing")
        else "unavailable"
        if error
        else "connected"
        if connected
        else "configured"
    )
    return {"configured": True, "connected": connected, "connection_status": status, "error": error}


def validate_model(name):
    if not name:
        raise HTTPException(422, "Pilih combo 9Router.")
    try:
        config = configuration()
    except ConfigError as error:
        raise HTTPException(503, str(error))
    saved = read_cache(config)
    schedule()
    if not saved.get("fetched_at"):
        raise HTTPException(409, "Katalog 9Router sedang dimuat. Tunggu lalu coba lagi.")
    if name not in {m["id"] for m in saved.get("models", [])}:
        raise HTTPException(
            422, "Combo tidak tercantum di katalog 9Router. Perbarui katalog dan pilih kembali."
        )


def generate(
    model, contents, config, check=lambda: None, on_connection=lambda label: None, validate=None
):
    router = configuration()
    # Historical Gemini jobs require an explicit combo selection.
    if model.startswith("gemini-"):
        raise ConfigError(
            "Pekerjaan lama menunggu pemilihan combo. Pilih combo lalu tekan Lanjutkan dengan 9Router."
        )
    schema = config.get("response_json_schema") or config.get("response_schema")
    if hasattr(schema, "model_json_schema"):
        schema = schema.model_json_schema()
    prompt = (
        contents
        + "\nKembalikan satu objek JSON valid tanpa markdown. Skema hasil:\n"
        + json.dumps(schema or {}, ensure_ascii=False)
    )
    check()
    on_connection(model)
    try:
        with client(router, httpx.Timeout(300, connect=10)) as http:
            response = http.post(
                router.url + "/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "stream": False,
                    "max_tokens": 12000,
                },
            )
        check()
        if response.status_code >= 400:
            raise _error(response)
        content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        if not isinstance(content, str):
            raise ValueError("Missing content")
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", content)
        if validate:
            validate(content)
        else:
            json.loads(content)
        return SimpleNamespace(text=content)
    except httpx.RequestError as error:
        raise ProviderWait(
            "9Router tidak dapat dijangkau atau permintaan terputus. Periksa layanan dan alamat Windows/WSL."
        ) from error
    except (KeyError, IndexError, ValueError) as error:
        raise RuntimeError(
            "Hasil analisis 9Router tidak sesuai skema JSON. Tahap dihentikan tanpa membuat highlight palsu."
        ) from error
