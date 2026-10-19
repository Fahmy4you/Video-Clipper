"""Discover models and verify structured generation against the configured account."""
from threading import Lock
from time import monotonic, time
import hashlib,json
from concurrent.futures import ThreadPoolExecutor
from .config import STORAGE
from .schemas import Highlights,gemini_highlight_config
from fastapi import HTTPException
from google import genai
from .config import settings

_lock=Lock()
_cache=None
_expires=0.0
_cache_key=None
_probe_lock=Lock()

def cache_path():
    fingerprint=hashlib.sha256(settings.gemini_api_key.encode()).hexdigest()[:24]
    return STORAGE/'model-access'/f'{fingerprint}.json'

def access_records():
    try:return json.loads(cache_path().read_text())
    except (OSError,ValueError):return {}

def record_access(name,ok):
    with _probe_lock:
        values=access_records();values[name]={'ok':ok,'until':time()+(3600 if ok else 300)}
        path=cache_path();path.parent.mkdir(exist_ok=True)
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(values));tmp.replace(path)

def record_unavailable(name):
    global _cache
    record_access(name,False)
    with _lock:
        if _cache is not None:_cache=[m for m in _cache if m['id']!=name]

def verified_model(option,refresh=False):
    record=access_records().get(option['id'],{})
    if not refresh and record.get('until',0)>time():return record.get('ok',False)
    try:
        with genai.Client(api_key=settings.gemini_api_key,http_options={'timeout':20000}) as client:
            response=client.models.generate_content(model=option['id'],contents='Compatibility check. Return JSON with clips: [] and unmet_requests: []. No explanations.',config={**gemini_highlight_config(),'max_output_tokens':1024})
            Highlights.model_validate_json(response.text)
        ok=True
    except Exception:ok=False
    record_access(option['id'],ok)
    return ok

def text_models(models):
    result={}
    for model in models:
        name=(model.name or '').removeprefix('models/')
        if not name.startswith('gemini-') or 'generateContent' not in (model.supported_actions or []): continue
        # The API lists specialized generation models too; these are not transcript analyzers.
        if any(part in name.lower() for part in ('image','tts','audio','live','robotics','computer-use','banana','transcribe')): continue
        result[name]={'id':name,'name':model.display_name or name}
    return sorted(result.values(),key=lambda item:item['name'].lower())

def available_models(refresh=False):
    global _cache,_expires,_cache_key
    if not settings.gemini_api_key:
        raise HTTPException(503,'Isi GEMINI_API_KEY di .env lalu restart aplikasi untuk memuat pilihan model.')
    with _lock:
        if not refresh and _cache is not None and _cache_key==settings.gemini_api_key and monotonic()<_expires:
            return list(_cache)
        try:
            with genai.Client(api_key=settings.gemini_api_key,http_options={'timeout':15000}) as client:
                options=text_models(client.models.list())
        except Exception as error:
            code=getattr(error,'code',None)
            if code in (400,401,403):
                message='Gemini menolak akses daftar model. Periksa API key dan izin akun, lalu muat ulang.'
            elif code==429:
                message='Batas permintaan Gemini tercapai. Tunggu sebentar lalu muat ulang daftar model.'
            else:
                message='Daftar model Gemini belum dapat dimuat. Periksa koneksi lalu coba lagi.'
            raise HTTPException(503,message) from None
        with ThreadPoolExecutor(max_workers=4) as pool:
            verified=list(pool.map(lambda option:verified_model(option,refresh),options))
        options=[option for option,ok in zip(options,verified) if ok]
        if not options:raise HTTPException(503,'Belum ada model yang berhasil merespons JSON dengan API key ini. Periksa akses/kuota, lalu periksa ulang model.')
        _cache=options;_cache_key=settings.gemini_api_key;_expires=monotonic()+300
        return list(options)

def validate_model(name):
    if name not in {model['id'] for model in available_models()}:
        raise HTTPException(422,'Model tidak tersedia untuk analisis teks. Muat ulang daftar lalu pilih model lain.')
    return name
