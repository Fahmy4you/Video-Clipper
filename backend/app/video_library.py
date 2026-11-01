"""Shared footage library with permanent, reference-checked deletion."""
import json,math,shutil
from pathlib import Path
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,File,UploadFile,Form,HTTPException
from fastapi.responses import FileResponse
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,model_validator
from sqlalchemy import select
from .hashtags import Hashtags,filter_library
from .instansi_api import source_owners,filter_sources
from .db import Session,session,VideoClip,Hashtag,Clip,Job,Instansi
from .config import STORAGE,settings
from .media import run,probe,write_json
from .queue_runtime import PENDING,add_library,wake
router=APIRouter(prefix='/api/video-clips')
def folder(aid):return STORAGE/'video-clips'/str(UUID(aid))
def info(v):
    return {**{c.name:(getattr(v,c.name).isoformat() if hasattr(getattr(v,c.name),'isoformat') else getattr(v,c.name)) for c in v.__table__.columns},'scope':v.scope or 'global','instansi_ids':v.instansi_ids,'instansi_names':sorted((i.name for i in v.instansi_records),key=str.casefold),'hashtags':v.hashtags,'hashtag_ids':[tag.id for tag in v.tag_records],'frames':math.floor(v.duration*30),'source_url':f'/api/video-clips/{v.id}/media/original','proxy_url':f'/api/video-clips/{v.id}/media/proxy.mp4','thumbnail_url':f'/api/video-clips/{v.id}/media/thumb.jpg','thumbnail_base':f'/api/video-clips/{v.id}/media/thumbs/'}
def lookup(s,aid):
    v=s.get(VideoClip,aid)
    if v is None:raise HTTPException(404,'Video koleksi tidak ditemukan.')
    return v
def snapshot(s,tags=None,instansi_ids=None,include_global=True):
    rows=[info(v) for v in s.scalars(select(VideoClip).where(VideoClip.archived==False,VideoClip.status=='ready').order_by(VideoClip.created_at))]
    return filter_library(filter_sources(rows,instansi_ids or [],include_global),tags or [])
class Scene(BaseModel):
    start:int=Field(ge=0);end:int=Field(gt=0);explain:str=Field(min_length=1,max_length=2000)
    @model_validator(mode='after')
    def bounds(self):
        if self.end<=self.start:raise ValueError('Rentang adegan tidak valid.')
        return self
class Metadata(BaseModel):
    scope:Literal['global','instansi']|None=None
    instansi_ids:list[UUID]|None=Field(default=None,max_length=100)
    @model_validator(mode='after')
    def ownership(self):
        if self.instansi_ids is not None:self.instansi_ids=list(dict.fromkeys(self.instansi_ids))
        if self.scope=='global' and self.instansi_ids:raise ValueError('Video Global tidak memiliki instansi.')
        if self.scope=='instansi' and not self.instansi_ids:raise ValueError('Pilih minimal satu instansi pemilik video.')
        if self.scope is None and self.instansi_ids is not None:raise ValueError('Pilih lingkup video.')
        return self
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=200)
    hashtags:Hashtags=Field(default_factory=list)
    hashtag_ids:list[UUID]|None=Field(default=None,max_length=30)
    explain:str=Field(default='',max_length=4000)
    scenes:list[Scene]=Field(default_factory=list,max_length=100)
    revision:int=Field(ge=1)
from datetime import datetime
class VideoClipView(BaseModel):
    id:str
    title:str
    url_path:str
    scope:Literal['global','instansi']
    instansi_ids:list[str]=Field(default_factory=list)
    instansi_names:list[str]=Field(default_factory=list)
    hashtags:list[str]
    hashtag_ids:list[str]
    explain:str
    scenes:list[Scene]
    duration:float
    frames:int
    width:int
    height:int
    status:str
    error:str|None=None
    archived:bool
    revision:int
    created_at:datetime
    source_url:str
    proxy_url:str
    thumbnail_url:str
    thumbnail_base:str
@router.get('',response_model=list[VideoClipView])
def listing(q:str='',include_archived:bool=False,s=Depends(session)):
    rows=s.scalars(select(VideoClip).order_by(VideoClip.created_at.desc())).all()
    return [info(v) for v in rows if (include_archived or not v.archived) and (not q or q.casefold() in (v.title+' '+' '.join('#'+tag for tag in v.hashtags)+' '+v.explain).casefold())]
@router.post('',status_code=202,response_model=VideoClipView)
async def upload(file:UploadFile=File(...),title:str=Form('Video'),scope:Literal['global','instansi']=Form(...),instansi_ids:list[UUID]=Form(default=[]),s=Depends(session)):
    owners=source_owners(s,scope,instansi_ids)
    aid=str(uuid4());root=folder(aid);root.mkdir(parents=True);path=root/'source.media';size=0
    try:
        with path.open('wb') as f:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>settings.library_max_mb*1024*1024:raise HTTPException(413,f'Video maksimal {settings.library_max_mb} MB.')
                f.write(chunk)
        if not size:raise HTTPException(422,'File kosong.')
        v=VideoClip(id=aid,scope=scope,instansi_records=owners,title=(title.strip() or Path(file.filename or 'Video').stem)[:200],url_path=str(path.relative_to(STORAGE)))
        s.add(v);s.flush();add_library(s,v.id);s.commit();wake();return info(v)
    except Exception:
        if not s.get(VideoClip,aid):path.unlink(missing_ok=True)
        raise
@router.patch('/{aid}',response_model=VideoClipView)
def edit(aid:str,body:Metadata,s=Depends(session)):
    v=s.scalar(select(VideoClip).where(VideoClip.id==aid).with_for_update())
    if not v:raise HTTPException(404)
    if v.revision!=body.revision:raise HTTPException(409,'Koleksi telah berubah. Muat ulang sebelum menyimpan.')
    if any(x.end>math.floor(v.duration*30) for x in body.scenes):raise HTTPException(422,'Adegan melewati akhir video.')
    if body.hashtag_ids is not None:
        wanted={str(id) for id in body.hashtag_ids}
        tags=list(s.scalars(select(Hashtag).where(Hashtag.id.in_(wanted)).with_for_update(read=True)))
        if len(tags)!=len(wanted):raise HTTPException(422,'Hashtag sudah dihapus atau tidak ditemukan. Muat ulang daftar.')
    else:
        wanted=set(body.hashtags)
        tags=list(s.scalars(select(Hashtag).where(Hashtag.name_tag.in_(wanted)).with_for_update(read=True)))
        if len(tags)!=len(wanted):raise HTTPException(422,'Buat hashtag terlebih dahulu pada halaman Hashtag.')
    if body.scope is not None:
        v.instansi_records=source_owners(s,body.scope,body.instansi_ids or []);v.scope=body.scope
    v.tag_records=tags
    for k,value in body.model_dump(exclude={'revision','hashtags','hashtag_ids','scope','instansi_ids'}).items():setattr(v,k,value)
    v.revision+=1;s.commit();return info(v)
def plan_asset_ids(plan):
    return {item['asset_id'] for segment in (plan or {}).get('segments',[])
            for item in segment.get('broll',[]) if item.get('asset_id')}

def lock_plan_assets(s,plan):
    # Saves/enqueues share-lock sources until commit. Deletion takes the exclusive
    # lock before inspecting references, so a concurrent edit cannot save a dead ID.
    wanted=plan_asset_ids(plan)
    if not wanted:return
    found=set(s.scalars(select(VideoClip.id).where(VideoClip.id.in_(wanted)).order_by(VideoClip.id).with_for_update(read=True)))
    if found!=wanted:raise HTTPException(409,'Video sisipan sudah dihapus. Muat ulang koleksi lalu ganti atau hapus sisipan yang tidak tersedia.')

def live_job_payload(s,payload):
    payload=dict(payload or {})
    lock_plan_assets(s,payload.get('plan'))
    if 'library' in payload:
        if payload.get('visual_mode')=='mix' and payload.get('source_policy_version')!=1:
            from .db import Project
            project=s.get(Project,payload.get('project_id')) if payload.get('project_id') else None
            owners=list(s.scalars(select(Instansi.id).where(Instansi.name_key.in_(['cryptowave','akademi crypto']))))
            payload.update(source_policy_version=1,instansi_ids=project.instansi_ids if project else owners,include_global=project.include_global if project else False)
            current={v.id:v for v in s.scalars(select(VideoClip).where(VideoClip.id.in_([x['id'] for x in payload['library']]))) }
            payload['library']=[{**x,'scope':current[x['id']].scope,'instansi_ids':current[x['id']].instansi_ids} for x in payload['library'] if x['id'] in current]
        if payload.get('source_policy_version')==1:payload['library']=filter_library(filter_sources(payload['library'],payload.get('instansi_ids',[]),payload.get('include_global',True)),payload.get('mix_hashtags',[]))
        wanted={item['id'] for item in payload['library']}
        existing=set(s.scalars(select(VideoClip.id).where(VideoClip.id.in_(wanted)).order_by(VideoClip.id).with_for_update(read=True))) if wanted else set()
        payload['library']=[item for item in payload['library'] if item['id'] in existing]
        # Old retry caches can contain a previously selected, now deleted source.
        # Recompute those suggestions using only the surviving snapshot candidates.
        payload['mix_results']={cid:plan for cid,plan in payload.get('mix_results',{}).items() if plan_asset_ids(plan)<=existing}
    return payload

@router.delete('/{aid}')
def remove(aid:str,s=Depends(session)):
    v=s.scalar(select(VideoClip).where(VideoClip.id==aid).with_for_update())
    if v is None:raise HTTPException(404,'Video koleksi tidak ditemukan.')
    if v.status in ('queued','processing'):raise HTTPException(409,'Video masih diproses. Tunggu proses selesai sebelum menghapusnya.')
    references=[title for title,plan,legacy in s.execute(select(Clip.title,Clip.plan,Clip.legacy_plan)) if aid in plan_asset_ids(plan)|plan_asset_ids(legacy)]
    if references:raise HTTPException(409,f'Video masih dipakai oleh {len(references)} highlight, termasuk “{references[0][:100]}”. Ganti atau hapus video sisipan tersebut di studio sebelum menghapus video koleksi.')
    for payload in s.scalars(select(Job.payload).where(Job.status.in_(PENDING))):
        if aid in plan_asset_ids(payload.get('plan')) or any(item.get('id')==aid for item in payload.get('library',[])) or any(aid in plan_asset_ids(plan) for plan in payload.get('mix_results',{}).values()):
            raise HTTPException(409,'Video masih dipakai pekerjaan aktif. Tunggu pekerjaan selesai atau batalkan sebelum menghapusnya.')
    try:canonical=str(UUID(aid))
    except ValueError:raise HTTPException(409,'Lokasi video koleksi tidak valid.')
    parent=STORAGE/'video-clips'
    if parent.is_symlink():raise HTTPException(409,'Lokasi koleksi tidak valid.')
    parent=parent.resolve();root=parent/canonical
    if root.is_symlink() or root.resolve().parent!=parent or (root.exists() and not root.is_dir()):raise HTTPException(409,'Lokasi video koleksi tidak valid.')
    trash=parent/('.delete-'+canonical+'-'+str(uuid4()));moved=False
    try:
        if root.exists():root.rename(trash);moved=True
        s.delete(v);s.commit()
    except Exception:
        s.rollback()
        if moved:trash.rename(root)
        raise
    cleanup_pending=False
    if moved:
        try:shutil.rmtree(trash)
        except OSError:cleanup_pending=True
    return {'deleted':aid,'cleanup_pending':cleanup_pending}
@router.post('/{aid}/retry',status_code=202,response_model=VideoClipView)
def retry(aid:str,s=Depends(session)):
    v=lookup(s,aid)
    if v.status not in ('failed',):raise HTTPException(409,'Video tidak sedang gagal.')
    v.status='queued';v.error=None;add_library(s,aid);s.commit();wake();return info(v)
@router.get('/{aid}/media/{name:path}')
def media(aid:str,name:str,s=Depends(session)):
    import re
    lookup(s,aid)
    if name=='original':
        p=folder(aid)/'source.media'
        if not p.is_file():raise HTTPException(404)
        return FileResponse(p,media_type=source_media_type(str(p),p.stat().st_mtime_ns))
    if name not in ('proxy.mp4','thumb.jpg') and not re.fullmatch(r'thumbs/[0-9]{5}\.jpg',name):raise HTTPException(404)
    p=folder(aid)/name
    if not p.is_file():raise HTTPException(404)
    return FileResponse(p)
def dispatch(aid):
    with Session() as s:add_library(s,aid);s.commit()
    wake()

def prepare(aid,check=lambda:None):
    with Session() as s:
        v=lookup(s,aid);v.status='processing';v.error=None;s.commit()
    try:
        root=folder(aid);src=root/'source.media';meta=probe(src);video=next((x for x in meta['streams'] if x['codec_type']=='video'),None);duration=float(meta['format'].get('duration',0))
        if not video or not math.isfinite(duration) or not 0<duration<=settings.library_max_duration:raise RuntimeError(f'Gunakan video valid dengan durasi maksimal {settings.library_max_duration/60:g} menit.')
        run(['ffmpeg','-y','-v','error','-threads','2','-i',str(src),'-an','-vf','scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30','-c:v','libx264','-threads','2','-preset','veryfast','-crf','26','-g','15','-movflags','+faststart',str(root/'proxy.partial.mp4')],check)
        (root/'proxy.partial.mp4').replace(root/'proxy.mp4');(root/'thumbs').mkdir(exist_ok=True)
        run(['ffmpeg','-y','-v','error','-i',str(root/'proxy.mp4'),'-vf','fps=1,scale=160:-2','-q:v','5',str(root/'thumbs/%05d.jpg')],check)
        import shutil
        if not (root/'thumbs/00001.jpg').exists():run(['ffmpeg','-y','-v','error','-i',str(root/'proxy.mp4'),'-frames:v','1','-vf','scale=160:-2',str(root/'thumbs/00001.jpg')],check)
        shutil.copyfile(root/'thumbs/00001.jpg',root/'thumb.jpg')
        metadata={'frames':math.floor(duration*30),'duration':duration,'width':video['width'],'height':video['height']};write_json(root/'metadata.json',metadata)
        with Session() as s:
            v=lookup(s,aid);v.duration=duration;v.width=video['width'];v.height=video['height'];v.status='ready';s.commit()
    except Exception as e:
        with Session() as s:
            v=lookup(s,aid);v.status='failed';v.error=str(e) if isinstance(e,RuntimeError) else 'Video gagal diproses. Periksa file lalu coba lagi.';s.commit()
        raise

from functools import lru_cache
@lru_cache(maxsize=128)
def source_media_type(path,mtime):
    meta=probe(path);fmt=meta.get('format',{}).get('format_name','')
    if any(x in fmt.split(',') for x in ('mov','mp4')):return 'video/mp4'
    if 'webm' in fmt:
        codecs={s.get('codec_name') for s in meta.get('streams',[])}
        return 'video/webm' if codecs <= {'vp8','vp9','av1','opus','vorbis'} else 'video/x-matroska'
    return {'avi':'video/x-msvideo','mpeg':'video/mpeg','ogg':'video/ogg'}.get(fmt,'application/octet-stream')
