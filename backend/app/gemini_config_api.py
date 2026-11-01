"""Sanitized local-only credential management endpoints."""
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field,ConfigDict,SecretStr
from uuid import uuid4
from sqlalchemy import select
from . import key_store as store,gemini_connections as pool,model_catalog as catalog
from .db import Session,Job,now
from .queue_runtime import WAITING,wake
from .schemas import GeminiConnectionView
router=APIRouter(prefix='/api/gemini-config',tags=['Gemini settings'])

class ConfigView(BaseModel):
    max_connections:int=store.MAX_CONNECTIONS
    revision:str
    connections:list[GeminiConnectionView]
class TestResult(BaseModel):
    ok:bool
    message:str

class Revision(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    revision:str
class Add(Revision):
    name:str=Field(min_length=1,max_length=40)
    key:SecretStr
class Edit(Revision):
    name:str=Field(min_length=1,max_length=40)
    key:SecretStr|None=None
class Order(Revision):
    ids:list[str]=Field(max_length=store.MAX_CONNECTIONS)
class Test(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model:str|None=Field(default=None,pattern=r'^gemini-[A-Za-z0-9._-]+$',max_length=200)

def public():
    _,revision=store.read()
    return {'revision':revision,'connections':pool.public_connections(),'max_connections':store.MAX_CONNECTIONS}

def changed():
    # Only model-capable new connections wake work. Other keys keep their cooldown.
    with Session() as s:
        touched=False
        for j in s.scalars(select(Job).where(Job.status.in_(WAITING)).with_for_update()):
            model=j.payload.get('gemini_model')
            if model and any(not pool.state(c).get('disabled') and catalog.can_use(c,model) and not pool.cooldown(pool.state(c),model) for c in pool.connections()):
                j.next_attempt_at=now();touched=True
        if touched:s.commit();wake()

def mutate(revision,change):
    try:store.save(revision,change)
    except store.KeyConflict as e:raise HTTPException(409,str(e)) from None
    except store.KeyConfigError as e:raise HTTPException(422,str(e)) from None
    except OSError:raise HTTPException(503,'File key tidak dapat disimpan. Periksa izin file backend.') from None
    changed();return public()

def verify_new(ident):
    c=next((c for c in pool.connections() if c.config_id==ident),None)
    if c:catalog.schedule(c)

@router.get('',response_model=ConfigView)
def get_config():
    catalog.schedule()
    return public()
@router.post('',status_code=201,response_model=ConfigView)
def add(body:Add):
    ident=str(uuid4())
    def change(rows):
        if len(rows)>=store.MAX_CONNECTIONS:raise store.KeyConfigError(f'Maksimal {store.MAX_CONNECTIONS} koneksi Gemini.')
        rows.append({'id':ident,'name':body.name,'key':body.key.get_secret_value(),'priority':next(n for n in range(1,store.MAX_CONNECTIONS+1) if n not in {r['priority'] for r in rows})})
    mutate(body.revision,change);verify_new(ident);return public()
@router.patch('/order',response_model=ConfigView)
def order(body:Order):
    def change(rows):
        if len(set(body.ids))!=len(body.ids) or set(body.ids)!={r['id'] for r in rows}:raise store.KeyConfigError('Urutan koneksi tidak cocok; muat ulang daftar.')
        for row in rows:row['priority']=body.ids.index(row['id'])+1
    return mutate(body.revision,change)
@router.patch('/{ident}',response_model=ConfigView)
def edit(ident:str,body:Edit):
    def change(rows):
        row=next((r for r in rows if r['id']==ident),None)
        if not row:raise HTTPException(404,'Koneksi tidak ditemukan.')
        row['name']=body.name
        if body.key is not None:row['key']=body.key.get_secret_value()
    result=mutate(body.revision,change)
    if body.key is not None:verify_new(ident);result=public()
    return result
@router.delete('/{ident}',response_model=ConfigView)
def remove(ident:str,body:Revision):
    def change(rows):
        found=next((r for r in rows if r['id']==ident),None)
        if not found:raise HTTPException(404,'Koneksi tidak ditemukan.')
        rows.remove(found)
        for n,row in enumerate(sorted(rows,key=lambda x:x['priority']),1):row['priority']=n
    return mutate(body.revision,change)
@router.post('/{ident}/test',status_code=202,response_model=TestResult)
def test(ident:str,body:Test|None=None):
    c=next((c for c in pool.connections() if c.config_id==ident),None)
    if not c:raise HTTPException(404,'Koneksi tidak ditemukan.')
    catalog.schedule(c,force=True)
    return {'ok':True,'message':'Pemeriksaan katalog dijadwalkan. Tidak mengirim prompt; status diperbarui di latar belakang.'}
