"""Root-level Gemini credentials. This module never returns secrets to public APIs."""
import fcntl,hashlib,json,os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from .config import ROOT,settings
MAX_CONNECTIONS=5
PATH=ROOT/'apikey.json'
MARKER=ROOT/'storage/runtime/gemini-json-initialized'

class KeyConfigError(RuntimeError):pass
class KeyConflict(KeyConfigError):pass

def validate(value,allow_empty_keys=False):
    if not isinstance(value,dict) or set(value)-{'version','connections'} or value.get('version')!=1:raise KeyConfigError('Format apikey.json tidak valid. Gunakan version 1 dan connections sesuai template.')
    rows=value.get('connections')
    if not isinstance(rows,list) or len(rows)>MAX_CONNECTIONS:raise KeyConfigError(f'apikey.json mendukung maksimal {MAX_CONNECTIONS} koneksi.')
    ids=set();keys=set();priorities=set();out=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)-{'id','name','key','priority'}:raise KeyConfigError('Struktur koneksi apikey.json tidak valid.')
        ident=row.get('id');name=row.get('name');key=row.get('key');priority=row.get('priority')
        if not isinstance(ident,str) or not 1<=len(ident)<=100 or ident in ids:raise KeyConfigError('ID koneksi wajib unik dan maksimal 100 karakter.')
        if not isinstance(name,str) or not 1<=len(name.strip())<=40:raise KeyConfigError('Nama koneksi wajib diisi, maksimal 40 karakter.')
        if not isinstance(key,str) or not key.strip() or len(key)>1000 or any(c.isspace() for c in key.strip()):raise KeyConfigError('API key wajib diisi tanpa spasi.')
        if type(priority) is not int or not 1<=priority<=MAX_CONNECTIONS or priority in priorities:raise KeyConfigError(f'Prioritas koneksi wajib unik, dari 1 sampai {MAX_CONNECTIONS}.')
        if key.strip() in keys:raise KeyConfigError('API key yang sama sudah digunakan.')
        ids.add(ident);keys.add(key.strip());priorities.add(priority);out.append({'id':ident,'name':name.strip(),'key':key.strip(),'priority':priority})
    return {'version':1,'connections':sorted(out,key=lambda x:x['priority'])}

@contextmanager
def locked():
    PATH.parent.mkdir(parents=True,exist_ok=True)
    lock=PATH.with_name(PATH.name+'.lock')
    fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(fd,'a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX);yield

def atomic(value):
    temporary=PATH.with_name(PATH.name+'.tmp')
    fd=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as handle:
        json.dump(value,handle,indent=2);handle.write('\n');handle.flush();os.fsync(handle.fileno())
    os.chmod(temporary,0o600);temporary.replace(PATH)

def read_unlocked():
    initialized=MARKER.exists()
    if not PATH.exists():
        rows=[];seen=set()
        for n,name in enumerate(('Utama','Cadangan 1','Cadangan 2') if not initialized else (),1):
            key=getattr(settings,'gemini_api_key'+('' if n==1 else '_'+str(n)),'').strip()
            if key and key not in seen:
                seen.add(key);rows.append({'id':str(uuid4()),'name':name,'key':key,'priority':n})
        atomic({'version':1,'connections':rows})
    if not initialized:
        MARKER.parent.mkdir(parents=True,exist_ok=True);MARKER.write_text('1\n')
    try:
        raw=PATH.read_bytes();value=validate(json.loads(raw))
    except (OSError,ValueError,UnicodeError):raise KeyConfigError('apikey.json tidak dapat dibaca atau JSON rusak. Perbaiki file sesuai template; key lama tidak dipakai kembali.') from None
    return value,hashlib.sha256(raw).hexdigest()

def read():
    try:
        with locked():return read_unlocked()
    except OSError:raise KeyConfigError('apikey.json tidak dapat diakses. Periksa izin file backend.') from None

def save(revision,change):
    with locked():
        value,current=read_unlocked()
        if revision!=current:raise KeyConflict('Konfigurasi key telah berubah. Muat ulang sebelum menyimpan.')
        change(value['connections']);value=validate(value);atomic(value)
    return read()
