"""Credential-scoped model access and bounded fallback; no credentials in state."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
from pathlib import Path
import fcntl,hashlib,json,random,re,time
from google import genai
from .config import settings,STORAGE

@dataclass
class Connection:
    id:str
    label:str
    priority:int
    key:str=field(repr=False)
    config_id:str=''

def connections():
    from .key_store import read
    value,_=read()
    return [Connection(hashlib.sha256(row['key'].encode()).hexdigest()[:24],row['name'],row['priority'],row['key'],row['id']) for row in value['connections']]

def redact(message):
    try:configured=connections()
    except RuntimeError:configured=[]
    for c in configured:message=message.replace(c.key,'[redacted]')
    return message

def state(c,patch=None):
    root=STORAGE/'gemini-connections';root.mkdir(parents=True,exist_ok=True)
    path=root/(c.id+'.json')
    with (root/(c.id+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:value=json.loads(path.read_text())
        except (OSError,ValueError):value={}
        if patch:
            patch(value);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value));tmp.replace(path)
        return value

class GeminiWait(Exception):
    def __init__(self,kind,next_at=None):
        self.kind=kind;self.next_at=next_at
        self.reason='Semua koneksi Gemini untuk model ini sedang menunggu kuota.' if kind=='waiting_quota' else 'Layanan Gemini belum tersedia. Hasil tahap sebelumnya tersimpan.'
        super().__init__(self.reason)

def client(c,timeout=300000):
    return genai.Client(api_key=c.key,http_options={'timeout':timeout,'retry_options':{'attempts':1}})

def classify(error):
    code=getattr(error,'code',None)
    # Inspect provider details only internally. Never persist the raw response.
    raw=str(getattr(error,'response_json',None) or getattr(error,'details',None) or error).lower()
    retry=None
    matches=re.findall(r'retry[_ ]?delay[\W]+([0-9.]+)s|retry after\s+([0-9.]+)',raw)
    if matches:retry=max(float(a or b) for a,b in matches)
    response=getattr(error,'response',None)
    header=getattr(response,'headers',{}).get('retry-after') if response is not None else None
    if header:
        try:retry=float(header)
        except ValueError:
            try:
                from email.utils import parsedate_to_datetime
                retry=max(0,parsedate_to_datetime(header).timestamp()-time.time())
            except Exception:pass
    if code==401 or any(t in raw for t in ('api_key_invalid','api key not valid','api key expired','api_key_service_blocked')):return 'invalid',None
    if code==429:return ('daily' if any(t in raw for t in ('perday','per_day','per day','daily')) else 'quota'),retry
    if code in (403,404):return 'unsupported',None
    if code in (408,500,502,503,504) or isinstance(error,(TimeoutError,ConnectionError,OSError)) or type(error).__name__ in ('ConnectError','ReadTimeout','ConnectTimeout','RemoteProtocolError'):return 'service',retry
    return 'request',None

def record_model(c,model,ok,name=None):
    def change(s):
        models=s.setdefault('runtime_models',{});old=models.get(model,{})
        models[model]={**old,'ok':ok,'name':name or old.get('name',model),'checked':time.time()}
        if ok:s['last_success']=time.time();s['disabled']=False;s['last_error']=None
    state(c,change)

def failure(c,model,kind,retry):
    def change(s):
        if kind=='invalid':s['disabled']=True;s['last_error']='Key tidak valid; perbaiki key di Pengaturan atau apikey.json.';return
        if kind=='unsupported':
            s.setdefault('runtime_models',{}).setdefault(model,{}).update(ok=False,checked=time.time());return
        if kind not in ('daily','quota','service'):return
        old=s.setdefault('cooldowns',{}).get(model,{})
        attempts=old.get('attempts',0)+1
        delay=retry if retry is not None else min(900,60*2**min(attempts-1,4)+random.uniform(0,5))
        s['cooldowns'][model]={'kind':'waiting_service' if kind=='service' else 'waiting_quota','until':None if kind=='daily' and retry is None else time.time()+max(1,delay),'attempts':attempts,'manual':kind=='daily' and retry is None}
    return state(c,change)

def cooldown(s,model):
    entries=[s.get('cooldowns',{}).get(k,{}) for k in ('*',model)]
    active=[x for x in entries if x and (x.get('manual') or x.get('until',0)>time.time())]
    if not active:return None
    if any(x.get('manual') for x in active):return next(x for x in active if x.get('manual'))
    return max(active,key=lambda x:x['until'])

def clear_expired_for_manual(model):
    # Explicit user action allows one new check, but does not override a known retry deadline.
    for c in connections():
        def change(s):
            if s.get('runtime_models',{}).get(model,{}).get('ok') is False:s['runtime_models'].pop(model,None)
            for key in ('*',model):
                item=s.get('cooldowns',{}).get(key)
                if item and item.get('manual'):s['cooldowns'].pop(key,None)
        state(c,change)

def generate(model,contents,config,check=lambda:None,on_connection=lambda label:None,validate=None):
    from .key_store import KeyConfigError
    if not connections():raise KeyConfigError('Belum ada koneksi Gemini. Tambahkan key di Pengaturan atau apikey.json untuk melanjutkan.')
    waiting=[];supported=False;attempted=set()
    while True:
        candidates=[candidate for candidate in connections() if candidate.id not in attempted]
        if not candidates:break
        c=candidates[0];attempted.add(c.id)
        check();s=state(c)
        if s.get('disabled'):continue
        from . import model_catalog as catalog
        access=s.get('runtime_models',{}).get(model,{})
        if access.get('ok') is False:continue
        if not catalog.listed(c,model):
            catalog.schedule(c)
            metadata=catalog.read_cache(c)
            if not metadata.get('fetched_at') or catalog.refreshing(c):
                waiting.append({'kind':'waiting_service','until':time.time()+60})
            continue
        supported=True
        blocked=cooldown(s,model)
        if blocked:waiting.append(blocked);continue
        on_connection(c.label)
        for attempt in range(3):
            check()
            if not any(current.id==c.id for current in connections()):break
            try:
                with client(c) as api:
                    response=api.models.generate_content(model=model,contents=contents,config=config)
                check()
                if validate is not None:
                    validate(response.text)
                    record_model(c,model,True)
                state(c,lambda s:s.setdefault('cooldowns',{}).pop(model,None))
                return response
            except Exception as error:
                from .media import Cancelled
                if isinstance(error,Cancelled):raise
                kind,retry=classify(error)
                if kind=='request':raise RuntimeError('Gemini menolak permintaan atau hasilnya tidak valid. Periksa model dan payload; koneksi tidak diganti.') from None
                if kind=='service' and attempt<2 and (retry is None or retry<=8):
                    deadline=time.monotonic()+(retry if retry is not None else 2**attempt+random.uniform(0,.5))
                    while time.monotonic()<deadline:check();time.sleep(min(.25,max(0,deadline-time.monotonic())))
                    continue
                new=failure(c,model,kind,retry);blocked=cooldown(new,model)
                if blocked:waiting.append(blocked)
                break
    if not connections():raise KeyConfigError('Semua koneksi Gemini telah dilepas. Tambahkan koneksi untuk melanjutkan pekerjaan.')
    if waiting:
        times=[x['until'] for x in waiting if x.get('until') is not None]
        raise GeminiWait('waiting_quota' if any(x['kind']=='waiting_quota' for x in waiting) else 'waiting_service',min(times) if times else None)
    raise RuntimeError('Tidak ada koneksi Gemini valid yang mendukung model pilihan. Periksa konfigurasi atau pilih model lain; model tidak diubah otomatis.')

def public_connections():
    from .model_catalog import read_cache,refreshing,_iso
    result=[]
    for c in connections():
        active=refreshing(c);data=read_cache(c);s=state(c)
        blocked=[(m,v) for m,v in s.get('cooldowns',{}).items() if v.get('manual') or (v.get('until') or 0)>time.time()]
        used=[m for m,v in s.get('runtime_models',{}).items() if v.get('ok')]
        result.append({'id':c.config_id or c.id,'label':c.label,'masked_key':'••••••••','priority':c.priority,
          'status':'invalid' if s.get('disabled') else 'waiting' if blocked else 'used' if used else 'catalog' if data.get('fetched_at') else 'unverified',
          'models':[m['id'] for m in data.get('models',[])],'used_models':used,'catalog_refreshing':active,'catalog_error':data.get('error'),'catalog_fetched_at':_iso(data.get('fetched_at')),
          'cooldowns':[{'model':m,'status':v['kind'],'next_attempt_at':_iso(v.get('until'))} for m,v in blocked]})
    return result
