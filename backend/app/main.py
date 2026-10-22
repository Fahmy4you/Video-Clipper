import json
import shutil
from pathlib import Path
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, text, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .db import session, engine, Project, Clip, Job
from .schemas import ProjectInput, ClipInput, ClipUpdate, ProjectView, ClipView, JobView, ModelSelection, ModelOption
from .media import project_dir
from .tasks import execute, celery
from .timeline import upgrade_plan, EditPlanV2
from .audio_assets import AudioImport,MAX_BYTES,audio_metadata
from .model_catalog import available_models, validate_model

app=FastAPI(title='Video Clipping API',version='0.1.0')
from .hashtag_api import router as hashtag_router
from .video_library import router as library_router,snapshot as library_snapshot,folder as library_folder,lock_plan_assets,live_job_payload
app.include_router(library_router)
app.include_router(hashtag_router)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost','127.0.0.1','testserver'])
@app.middleware('http')
async def local_origin(request, call_next):
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in ('http://localhost:5173','http://127.0.0.1:5173','http://localhost:8000','http://127.0.0.1:8000'):
        return JSONResponse(status_code=403,content={'detail':'Origin tidak diizinkan.'})
    return await call_next(request)

@app.exception_handler(SQLAlchemyError)
async def database_error(request,exc):
    return JSONResponse(status_code=503,content={'detail':'Koneksi PostgreSQL sedang terganggu atau sibuk. Draft lokal tetap tersimpan. Tunggu sebentar lalu coba lagi; konfigurasi tidak perlu diisi ulang.'})
def get(s,model,id):
    item=s.get(model,id)
    if item is None: raise HTTPException(404,'Data tidak ditemukan.')
    return item
def serialize(obj): return {c.name:getattr(obj,c.name) for c in obj.__table__.columns}
@app.get('/api/health')
def health():
    database='not_configured'
    if engine:
        try:
            with engine.connect() as c: c.execute(text('SELECT 1 FROM projects LIMIT 1'))
            database='ready'
        except SQLAlchemyError: database='unavailable'
    try:
        import redis
        redis.Redis.from_url(settings.redis_url,socket_connect_timeout=1,socket_timeout=1).ping(); queue=True
    except Exception: queue=False
    return {'database':database,'redis':queue,'ffmpeg':bool(shutil.which('ffmpeg')),'gemini':bool(settings.gemini_api_key)}
@app.get('/api/models',response_model=list[ModelOption])
def models(refresh:bool=False):
    return available_models(refresh)
@app.get('/api/projects',response_model=list[ProjectView])
def projects(s:DBSession=Depends(session)):
    return [serialize(x) for x in s.scalars(select(Project).order_by(Project.created_at.desc()))]
@app.post('/api/projects',status_code=201,response_model=ProjectView)
def create_project(body:ProjectInput,s:DBSession=Depends(session)):
    validate_model(body.gemini_model)
    p=Project(**body.model_dump()); s.add(p); s.commit(); return serialize(p)
@app.delete('/api/projects/{id}')
def delete_project(id:str,s:DBSession=Depends(session)):
    from uuid import uuid4
    from .config import STORAGE
    p=s.scalar(select(Project).where(Project.id==id).with_for_update())
    if p is None:raise HTTPException(404,'Proyek tidak ditemukan.')
    if s.scalar(select(Job.id).where(Job.project_id==id,Job.status.in_(['queued','running']))):
        raise HTTPException(409,'Tunggu pekerjaan proyek selesai atau batalkan sebelum menghapus proyek.')
    try:canonical=str(UUID(id))
    except ValueError:raise HTTPException(409,'Lokasi proyek tidak valid.')
    parent=(STORAGE/'projects').resolve();folder=parent/canonical
    if folder.is_symlink() or folder.resolve().parent!=parent:raise HTTPException(409,'Lokasi proyek tidak valid.')
    clip_ids=list(s.scalars(select(Clip.id).where(Clip.project_id==id)))
    trash=parent/('.delete-'+canonical+'-'+str(uuid4()));moved=False
    try:
        if folder.exists():folder.rename(trash);moved=True
        s.execute(delete(Job).where(Job.project_id==id))
        s.execute(delete(Clip).where(Clip.project_id==id))
        s.delete(p);s.commit()
    except Exception:
        s.rollback()
        if moved:trash.rename(folder)
        raise
    cleanup_pending=False
    if moved:
        try:shutil.rmtree(trash)
        except OSError:cleanup_pending=True
    return {'deleted':id,'clip_ids':clip_ids,'cleanup_pending':cleanup_pending}

@app.get('/api/projects/{id}',response_model=ProjectView)
def project(id:str,s:DBSession=Depends(session)): return serialize(get(s,Project,id))
@app.patch('/api/projects/{id}/model',response_model=ProjectView)
def project_model(id:str,body:ModelSelection,s:DBSession=Depends(session)):
    p=get(s,Project,id)
    validate_model(body.gemini_model)
    p.gemini_model=body.gemini_model;s.commit();return serialize(p)
@app.get('/api/projects/{id}/clips',response_model=list[ClipView])
def clips(id:str,s:DBSession=Depends(session)):
    get(s,Project,id)
    return [serialize(x) for x in s.scalars(select(Clip).where(Clip.project_id==id))]
@app.get('/api/projects/{id}/transcript')
def transcript(id:str,s:DBSession=Depends(session)):
    get(s,Project,id); f=project_dir(id)/'transcript.json'
    return json.loads(f.read_text()) if f.exists() else {'words':[]}
@app.get('/api/projects/{id}/jobs',response_model=list[JobView])
def jobs(id:str,s:DBSession=Depends(session)):
    return [serialize(x) for x in s.scalars(select(Job).where(Job.project_id==id).order_by(Job.created_at.desc()))]
def enqueue(s,pid,kind,clip=None,payload=None):
    # Serialize competing enqueue requests for the same project.
    s.execute(select(Project).where(Project.id==pid).with_for_update()).scalar_one()
    active=s.scalar(select(Job).where(Job.project_id==pid,Job.status.in_(['queued','running'])))
    if active: raise HTTPException(409,'Proyek ini masih memiliki pekerjaan aktif.')
    j=Job(project_id=pid,kind=kind,clip_id=clip,payload=live_job_payload(s,payload))
    s.add(j); s.commit()
    try: execute.apply_async(args=[j.id],task_id=j.id,retry=False)
    except Exception:
        j.status='failed'; j.error='Antrean tidak tersedia. Jalankan Redis dan worker.'; s.commit()
        raise HTTPException(503,j.error)
    return serialize(j)
@app.post('/api/projects/{id}/analysis',status_code=202)
def analysis(id:str,s:DBSession=Depends(session)):
    p=get(s,Project,id)
    if not p.gemini_model: raise HTTPException(422,'Pilih model Gemini untuk proyek ini terlebih dahulu.')
    validate_model(p.gemini_model)
    return enqueue(s,id,'analysis',payload={'gemini_model':p.gemini_model,'aspect_ratio':p.aspect_ratio,'highlight_count':p.highlight_count,'additional_prompt':p.additional_prompt,'visual_mode':p.visual_mode,'mix_hashtags':p.mix_hashtags,'library':library_snapshot(s,p.mix_hashtags) if p.visual_mode=='mix' else []})
def validate_plan(plan,project):
    v2=upgrade_plan(plan.model_dump())
    if any(x['source_in']+x['duration']>round(project.duration*30) for x in v2['segments']):raise HTTPException(422,'Clip melebihi durasi sumber.')
    for segment in v2['segments']:
        for item in segment.get('broll',[]):
            try:meta=json.loads((library_folder(item['asset_id'])/'metadata.json').read_text())
            except (ValueError,OSError):raise HTTPException(422,'Video sisipan tidak tersedia.')
            if item['source_in']+item['end']-item['start']>meta['frames']:raise HTTPException(422,'Sisipan melewati akhir video koleksi.')
        for audio in segment.get('audio',[]):
            try:metadata=audio_metadata(project_dir(project.id),audio['asset_id'])
            except (ValueError,OSError):raise HTTPException(422,'Audio tidak ditemukan pada proyek ini.')
            if audio['source_in']+audio['end']-audio['start']>metadata['frames']:raise HTTPException(422,'Potongan audio melebihi durasi aset.')
        for overlay in segment['overlays']:
            if overlay['kind']=='image':
                try:asset=str(UUID(overlay['asset_id']))
                except ValueError:raise HTTPException(422,'ID gambar tidak valid.')
                if not (project_dir(project.id)/'assets'/f'{asset}.png').is_file():raise HTTPException(422,'Gambar tidak ditemukan pada proyek ini.')

@app.post('/api/projects/{id}/clips',status_code=201,response_model=ClipView)
def manual_clip(id:str,body:ClipInput,s:DBSession=Depends(session)):
    p=get(s,Project,id)
    lock_plan_assets(s,body.plan.model_dump())
    validate_plan(body.plan,p)
    c=Clip(project_id=id,title=body.title,plan=upgrade_plan(body.plan.model_dump())); s.add(c); s.commit(); return serialize(c)
@app.patch('/api/clips/{id}',response_model=ClipView)
def save_clip(id:str,body:ClipUpdate,s:DBSession=Depends(session)):
    c=s.scalar(select(Clip).where(Clip.id==id).with_for_update())
    if c is None: raise HTTPException(404,'Clip tidak ditemukan.')
    if c.revision!=body.revision: raise HTTPException(409,'Clip sudah berubah. Muat ulang sebelum menyimpan.')
    p=get(s,Project,c.project_id)
    lock_plan_assets(s,body.plan.model_dump())
    validate_plan(body.plan,p)
    c.title=body.title; c.plan=upgrade_plan(body.plan.model_dump()); c.revision+=1; s.commit(); return serialize(c)
@app.post('/api/clips/{id}/preview',status_code=202)
def preview(id:str,s:DBSession=Depends(session)):
    c=get(s,Clip,id); return enqueue(s,c.project_id,'preview',c.id,{'plan':c.plan,'revision':c.revision,'aspect_ratio':get(s,Project,c.project_id).aspect_ratio})
@app.post('/api/clips/{id}/exports',status_code=202)
def export(id:str,s:DBSession=Depends(session)):
    c=get(s,Clip,id); return enqueue(s,c.project_id,'export',c.id,{'plan':c.plan,'revision':c.revision,'aspect_ratio':get(s,Project,c.project_id).aspect_ratio})
@app.get('/api/jobs/{id}',response_model=JobView)
@app.get('/api/exports/{id}',response_model=JobView)
def job(id:str,s:DBSession=Depends(session)): return serialize(get(s,Job,id))
@app.post('/api/jobs/{id}/cancel')
def cancel(id:str,s:DBSession=Depends(session)):
    j=s.scalar(select(Job).where(Job.id==id).with_for_update())
    if j is None: raise HTTPException(404,'Pekerjaan tidak ditemukan.')
    if j.status in ('queued','running'): j.status='cancelled'; j.stage='Dibatalkan'; s.commit()
    return serialize(j)
@app.post('/api/jobs/{id}/retry',status_code=202)
def retry(id:str,s:DBSession=Depends(session)):
    j=get(s,Job,id)
    if j.status not in ('failed','cancelled'): raise HTTPException(409,'Pekerjaan belum gagal atau dibatalkan.')
    payload=j.payload
    if j.kind=='analysis':
        p=get(s,Project,j.project_id)
        if not p.gemini_model: raise HTTPException(422,'Pilih model Gemini terlebih dahulu.')
        validate_model(p.gemini_model)
        payload={**j.payload,'gemini_model':p.gemini_model}
    return enqueue(s,j.project_id,j.kind,j.clip_id,payload)
@app.get('/api/media/{pid}/{filename}')
def media(pid:str,filename:str,s:DBSession=Depends(session)):
    get(s,Project,pid)
    if filename != 'source.mp4':
        try: UUID(Path(filename).stem)
        except ValueError: raise HTTPException(404)
    if Path(filename).name!=filename or not filename.endswith('.mp4'): raise HTTPException(404)
    f=project_dir(pid)/filename
    if not f.is_file(): raise HTTPException(404)
    return FileResponse(f,media_type='video/mp4')

@app.get('/api/projects/{id}/editor-media')
def editor_media(id:str,s:DBSession=Depends(session)):
    get(s,Project,id);f=project_dir(id)/'editor'/'manifest.json'
    if not f.exists():return {'status':'pending'}
    return {**json.loads(f.read_text()),'proxy_url':f'/api/editor-media/{id}/proxy.mp4','thumbnail_base':f'/api/editor-media/{id}/thumbs/'}
@app.post('/api/projects/{id}/editor-media',status_code=202)
def prepare_editor_media(id:str,s:DBSession=Depends(session)):
    get(s,Project,id)
    if not (project_dir(id)/'source.mp4').exists():raise HTTPException(409,'Video sumber belum tersedia.')
    return enqueue(s,id,'editor_media')
@app.get('/api/editor-media/{id}/{filename:path}')
def serve_editor_media(id:str,filename:str,s:DBSession=Depends(session)):
    import re
    get(s,Project,id)
    if filename!='proxy.mp4' and not re.fullmatch(r'thumbs/[0-9]{5}\.jpg',filename):raise HTTPException(404)
    f=project_dir(id)/'editor'/filename
    if not f.is_file():raise HTTPException(404)
    return FileResponse(f)
@app.get('/api/projects/{id}/assets')
def assets(id:str,s:DBSession=Depends(session)):
    get(s,Project,id);folder=project_dir(id)/'assets'
    return [json.loads(f.read_text()) for f in sorted(folder.glob('*.json'))] if folder.exists() else []
@app.post('/api/projects/{id}/assets',status_code=201)
async def upload_asset(id:str,file:UploadFile=File(...),s:DBSession=Depends(session)):
    from PIL import Image,ImageOps,UnidentifiedImageError
    from io import BytesIO
    from uuid import uuid4
    from .media import write_json
    get(s,Project,id)
    data=await file.read(20*1024*1024+1)
    if len(data)>20*1024*1024:raise HTTPException(413,'Gambar maksimal 20 MB.')
    try:
        im=Image.open(BytesIO(data))
        if im.format not in ('PNG','JPEG','WEBP') or getattr(im,'n_frames',1)!=1:raise HTTPException(422,'Gunakan PNG, JPEG, atau WebP statis.')
        if im.width*im.height>40000000:raise HTTPException(422,'Resolusi gambar terlalu besar (maksimal 40 megapiksel).')
        im=ImageOps.exif_transpose(im).convert('RGBA')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):raise HTTPException(422,'Gambar tidak valid.')
    aid=str(uuid4());folder=project_dir(id)/'assets';folder.mkdir(exist_ok=True)
    im.save(folder/f'{aid}.png')
    result={'id':aid,'name':Path(file.filename or 'Gambar').name[:200],'width':im.width,'height':im.height,'url':f'/api/assets/{id}/{aid}'}
    write_json(folder/f'{aid}.json',result);return result
@app.get('/api/assets/{id}/{asset_id}')
def asset(id:str,asset_id:str,s:DBSession=Depends(session)):
    get(s,Project,id)
    try:aid=str(UUID(asset_id))
    except ValueError:raise HTTPException(404)
    f=project_dir(id)/'assets'/f'{aid}.png'
    if not f.is_file():raise HTTPException(404)
    return FileResponse(f,media_type='image/png')

@app.delete('/api/clips/{id}')
def delete_clip(id:str,s:DBSession=Depends(session)):
    from uuid import uuid4
    c=get(s,Clip,id)
    s.execute(select(Project).where(Project.id==c.project_id).with_for_update()).scalar_one()
    c=s.scalar(select(Clip).where(Clip.id==id).with_for_update())
    if c is None:raise HTTPException(404,'Highlight tidak ditemukan.')
    if s.scalar(select(Job).where(Job.project_id==c.project_id,Job.status.in_(['queued','running']))):
        raise HTTPException(409,'Tunggu pekerjaan proyek selesai atau batalkan sebelum menghapus highlight.')
    folder=project_dir(c.project_id).resolve()
    jobs=list(s.scalars(select(Job).where(Job.clip_id==id)))
    targets=[]
    for job in jobs:
        jid=str(UUID(job.id))
        for name in (jid+'.mp4',jid+'.partial.mp4',jid+'-work'):
            path=folder/name
            if path.exists():
                if path.is_symlink() or path.resolve().parent!=folder:raise HTTPException(409,'Lokasi berkas highlight tidak valid.')
                targets.append(path)
    trash=folder/('.delete-'+str(uuid4()));trash.mkdir()
    moved=[]
    try:
        for path in targets:
            dest=trash/path.name;path.rename(dest);moved.append((path,dest))
        s.execute(delete(Job).where(Job.clip_id==id));s.delete(c);s.commit()
    except Exception:
        s.rollback()
        for path,dest in reversed(moved):dest.rename(path)
        trash.rmdir()
        raise
    shutil.rmtree(trash)
    return {'deleted':id,'files_deleted':len(targets)}

@app.get('/api/projects/{id}/audio-assets')
def list_audio_assets(id:str,s:DBSession=Depends(session)):
    get(s,Project,id);folder=project_dir(id)/'audio'
    return [json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))] if folder.exists() else []

@app.post('/api/projects/{id}/audio-assets/upload',status_code=202)
async def upload_audio(id:str,file:UploadFile=File(...),mode:str=Form('audio'),s:DBSession=Depends(session)):
    from uuid import uuid4
    get(s,Project,id)
    if mode not in ('audio','video'):raise HTTPException(422,'Pilih unggah audio atau ekstrak video.')
    folder=project_dir(id)/'audio-inbox';folder.mkdir(exist_ok=True);aid=str(uuid4());path=folder/f'{aid}.media';size=0
    try:
        with path.open('wb') as out:
            while data:=await file.read(1024*1024):
                size+=len(data)
                if size>MAX_BYTES:raise HTTPException(413,'Unggahan audio/video maksimal 200 MB.')
                out.write(data)
        if not size:raise HTTPException(422,'File kosong.')
        return enqueue(s,id,'audio_import',payload={'mode':mode,'asset_id':aid,'name':Path(file.filename or 'Audio').name[:200]})
    except Exception:path.unlink(missing_ok=True);raise

@app.post('/api/projects/{id}/audio-import',status_code=202)
def import_audio_url(id:str,body:AudioImport,s:DBSession=Depends(session)):
    from uuid import uuid4
    get(s,Project,id)
    return enqueue(s,id,'audio_import',payload={**body.model_dump(),'mode':'url','asset_id':str(uuid4())})

@app.get('/api/audio/{id}/{asset_id}')
def serve_audio(id:str,asset_id:str,s:DBSession=Depends(session)):
    get(s,Project,id)
    try:metadata=audio_metadata(project_dir(id),asset_id)
    except (ValueError,OSError):raise HTTPException(404,'Audio tidak ditemukan.')
    return FileResponse(project_dir(id)/'audio'/f'{str(UUID(asset_id))}.m4a',media_type='audio/mp4')

@app.post('/api/projects/{id}/mix',status_code=202)
def retry_mix(id:str,s:DBSession=Depends(session)):
    p=get(s,Project,id)
    prior=s.scalar(select(Job).where(Job.project_id==id,Job.kind.in_(['analysis','mix'])).order_by(Job.created_at.desc()))
    payload=prior.payload if prior and prior.payload.get('visual_mode')=='mix' else {'gemini_model':p.gemini_model,'visual_mode':'mix','mix_hashtags':p.mix_hashtags,'library':library_snapshot(s,p.mix_hashtags)}
    return enqueue(s,id,'mix',payload=payload)
