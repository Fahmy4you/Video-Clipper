"""Non-generating Gemini catalog. Metadata, inference history and cooldowns are separate."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from time import monotonic, time, sleep
import fcntl, json, os
from fastapi import HTTPException
from .config import STORAGE
from . import gemini_connections as pool

VERSION = 1
TTL = 86400
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='gemini-catalog')
_pending = {}
_lock = Lock()


def cache_path(connection):
    return STORAGE / 'model-catalog-v1' / (connection.id + '.json')


def read_cache(connection):
    try:
        data = json.loads(cache_path(connection).read_text())
        return data if isinstance(data,dict) and data.get('version') == VERSION else {}
    except (OSError, ValueError):
        return {}


def write_cache(connection, data):
    path = cache_path(connection)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as output:
        json.dump({'version': VERSION, **data}, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def text_models(models):
    result = {}
    for model in models:
        name = (model.name or '').removeprefix('models/')
        if not name.startswith('gemini-') or 'generateContent' not in (model.supported_actions or []):
            continue
        if any(part in name.lower() for part in ('image', 'tts', 'audio', 'live', 'robotics', 'computer-use', 'banana', 'transcribe', 'video', 'veo', 'embedding', 'omni')):
            continue
        result[name] = {'id': name, 'name': model.display_name or name}
    return sorted(result.values(), key=lambda item: item['name'].casefold())


def _lease(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BlockingIOError:
        handle.close()
        return None


def refreshing(connection):
    lease = _lease(cache_path(connection).with_suffix('.lock'))
    if lease is None:
        return True
    lease.close()
    return False


def _current(connection):
    return any(c.id == connection.id for c in pool.connections())


def on_refresh():
    # A successful discovery can make a waiting job eligible, without an inference probe.
    from .gemini_config_api import changed
    changed()


def _refresh(connection, lease):
    slot = None
    try:
        wait_until = monotonic() + 30
        while slot is None and monotonic() < wait_until:
            for number in range(2):
                slot = _lease(STORAGE / 'model-catalog-v1' / f'slot-{number}.lock')
                if slot is not None:
                    break
            if slot is None:
                sleep(.05)
        if slot is None or not _current(connection):
            return
        previous = read_cache(connection)
        try:
            deadline = monotonic() + 30
            models = []
            token = None
            seen = set()
            with pool.client(connection, 15000) as client:
                while True:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    config = {'page_size': 1000, 'http_options': {'timeout': max(1, int(min(15, remaining) * 1000))}}
                    if token:
                        config['page_token'] = token
                    page = client.models.list(config=config)
                    models.extend(page.page)
                    token = page.config.get('page_token')
                    if monotonic() > deadline:
                        raise TimeoutError()
                    if not token:
                        break
                    if token in seen:
                        raise RuntimeError('Repeated catalog page token')
                    seen.add(token)
            if not _current(connection):
                return
            write_cache(connection, {'models': text_models(models), 'fetched_at': time(), 'attempts': 0, 'error': None, 'next_attempt_at': None})
        except Exception as error:
            if not _current(connection):
                return
            kind, retry = pool.classify(error)
            attempts = previous.get('attempts', 0) + 1
            delay = max((60, 300, 900)[min(attempts - 1, 2)], retry or 0)
            if kind == 'invalid':
                pool.failure(connection, '*', 'invalid', None)
            messages = {'invalid': 'API key tidak valid.', 'unsupported': 'Akses katalog ditolak.', 'quota': 'Permintaan metadata dibatasi Google.', 'daily': 'Permintaan metadata dibatasi Google.'}
            write_cache(connection, {**previous, 'attempts': attempts, 'error': messages.get(kind, 'Katalog belum dapat diperbarui. Cache sebelumnya tetap tersedia.'), 'next_attempt_at': time() + delay, 'attempted_at': time()})
    finally:
        if slot:
            slot.close()
        lease.close()
    try:
        on_refresh()
    except Exception:
        # Discovery remains usable when the queue/database is temporarily offline.
        pass


def schedule(connection=None, force=False):
    conns = [connection] if connection else pool.connections()
    for c in conns:
        data = read_cache(c)
        if data.get('next_attempt_at', 0) and data['next_attempt_at'] > time():
            continue
        if not force and data.get('fetched_at', 0) > time() - TTL:
            continue
        ident = str(cache_path(c))
        with _lock:
            if ident in _pending and not _pending[ident].done():
                continue
            lease = _lease(cache_path(c).with_suffix('.lock'))
            if lease is not None:
                _pending[ident] = _executor.submit(_refresh, c, lease)


def listed(connection, model):
    return any(m['id'] == model for m in read_cache(connection).get('models', []))


def can_use(connection, model):
    state = pool.state(connection)
    observed = state.get('runtime_models', {}).get(model, {})
    return not state.get('disabled') and listed(connection, model) and observed.get('ok') is not False


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def snapshot(update=True):
    conns = pool.connections()
    if update:
        schedule()
    merged = {}
    connections = []
    for c in conns:
        active = refreshing(c)
        data = read_cache(c)
        state = pool.state(c)
        stale = data.get('fetched_at', 0) <= time() - TTL
        connections.append({'id': c.config_id, 'label': c.label, 'refreshing': active, 'stale': stale, 'fetched_at': _iso(data.get('fetched_at')), 'next_attempt_at': _iso(data.get('next_attempt_at')), 'error': data.get('error'), 'model_count': len(data.get('models', []))})
        for m in data.get('models', []):
            row = merged.setdefault(m['id'], {**m, 'connections': [], 'stale': True})
            observed = state.get('runtime_models', {}).get(m['id'], {})
            blocked = pool.cooldown(state, m['id'])
            status = 'denied' if state.get('disabled') or observed.get('ok') is False else blocked['kind'] if blocked else 'used' if observed.get('ok') else 'catalog'
            row['connections'].append({'id': c.config_id, 'label': c.label, 'status': status, 'next_attempt_at': _iso(blocked.get('until')) if blocked else None})
            row['stale'] = row['stale'] and stale
    for row in merged.values():
        statuses = {c['status'] for c in row['connections']}
        row['selectable'] = statuses != {'denied'}
        row['status'] = next((s for s in ('used', 'catalog', 'waiting_quota', 'waiting_service') if s in statuses), 'denied')
    return {'models': sorted(merged.values(), key=lambda m: m['name'].casefold()), 'connections': connections, 'refreshing': any(c['refreshing'] for c in connections), 'stale': any(c['stale'] for c in connections)}


def known_models():
    return snapshot(update=False)['models']


def available_models(refresh=False):
    if refresh:
        schedule(force=True)
    return snapshot()['models']


def validate_model(name):
    options = {m['id']: m for m in known_models()}
    if name not in options:
        schedule()
        if not options:
            raise HTTPException(409, 'Katalog model sedang dimuat. Tunggu pembaruan metadata, lalu coba lagi.')
        raise HTTPException(422, 'Model tidak tercantum di katalog koneksi yang tersedia. Perbarui katalog lalu pilih model.')
    if not options[name]['selectable']:
        raise HTTPException(422, 'Akses model ditolak oleh seluruh koneksi yang mencantumkannya. Periksa akses di AI Studio.')
    return name
