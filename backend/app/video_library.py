"""Shared, versioned footage library. Archived sources remain renderable."""
import json,math
from pathlib import Path
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,File,UploadFile,Form,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ConfigDict,model_validator
from sqlalchemy import select
from .hashtags import Hashtags,filter_library
from .db import Session,session,VideoClip,Hashtag
from .config import STORAGE,settings
from .media import run,probe,write_json
router=APIRouter(prefix='/api/video-clips')
def folder(aid):return STORAGE/'video-clips'/str(UUID(aid))
def info(v):
    return {**{c.name:(getattr(v,c.name).isoformat() if hasattr(getattr(v,c.name),'isoformat') else getattr(v,c.name)) for c in v.__table__.columns},'hashtags':v.hashtags,'hashtag_ids':[tag.id for tag in v.tag_records],'frames':math.floor(v.duration*30),'proxy_url':f'/api/video-clips/{v.id}/media/proxy.mp4','thumbnail_url':f'/api/video-clips/{v.id}/media/thumb.jpg','thumbnail_base':f'/api/video-clips/{v.id}/media/thumbs/'}
def lookup(s,aid):
    v=s.get(VideoClip,aid)
    if v is None:raise HTTPException(404,'Video koleksi tidak ditemukan.')
    return v
def snapshot(s,tags=None):return filter_library([info(v) for v in s.scalars(select(VideoClip).where(VideoClip.archived==False,VideoClip.status=='ready').order_by(VideoClip.created_at))],tags or [])
class Scene(BaseModel):
    start:int=Field(ge=0);end:int=Field(gt=0);explain:str=Field(min_length=1,max_length=2000)
    @model_validator(mode='after')
    def bounds(self):
        if self.end<=self.start:raise ValueError('Rentang adegan tidak valid.')
        return self
class Metadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=200)
    hashtags:Hashtags=Field(default_factory=list)
    hashtag_ids:list[UUID]|None=Field(default=None,max_length=30)
    explain:str=Field(default='',max_length=4000)
    scenes:list[Scene]=Field(default_factory=list,max_length=100)
    revision:int=Field(ge=1)
@router.get('')
def listing(q:str='',include_archived:bool=False,s=Depends(session)):
    rows=s.scalars(select(VideoClip).order_by(VideoClip.created_at.desc())).all()
    return [info(v) for v in rows if (include_archived or not v.archived) and (not q or q.casefold() in (v.title+' '+' '.join('#'+tag for tag in v.hashtags)+' '+v.explain).casefold())]
@router.post('',status_code=202)
async def upload(file:UploadFile=File(...),title:str=Form('Video'),s=Depends(session)):
    aid=str(uuid4());root=folder(aid);root.mkdir(parents=True);path=root/'source.media';size=0
    try:
        with path.open('wb') as f:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>settings.library_max_mb*1024*1024:raise HTTPException(413,f'Video maksimal {settings.library_max_mb} MB.')
                f.write(chunk)
        if not size:raise HTTPException(422,'File kosong.')
        v=VideoClip(id=aid,title=(title.strip() or Path(file.filename or 'Video').stem)[:200],url_path=str(path.relative_to(STORAGE)))
        s.add(v);s.commit();dispatch(v.id);return info(v)
    except Exception:
        if not s.get(VideoClip,aid):path.unlink(missing_ok=True)
        raise
@router.patch('/{aid}')
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
    v.tag_records=tags
    for k,value in body.model_dump(exclude={'revision','hashtags','hashtag_ids'}).items():setattr(v,k,value)
    v.revision+=1;s.commit();return info(v)
@router.delete('/{aid}')
def archive(aid:str,s=Depends(session)):
    v=lookup(s,aid);v.archived=True;v.revision+=1;s.commit();return {'archived':aid}
@router.post('/{aid}/retry',status_code=202)
def retry(aid:str,s=Depends(session)):
    v=lookup(s,aid)
    if v.status not in ('failed',):raise HTTPException(409,'Video tidak sedang gagal.')
    v.status='queued';v.error=None;s.commit();dispatch(aid);return info(v)
@router.get('/{aid}/media/{name:path}')
def media(aid:str,name:str,s=Depends(session)):
    import re
    lookup(s,aid)
    if name not in ('proxy.mp4','thumb.jpg') and not re.fullmatch(r'thumbs/[0-9]{5}\.jpg',name):raise HTTPException(404)
    p=folder(aid)/name
    if not p.is_file():raise HTTPException(404)
    return FileResponse(p)
def dispatch(aid):
    from .tasks import prepare_library
    try:prepare_library.apply_async(args=[aid],retry=False)
    except Exception:
        with Session() as s:
            v=s.get(VideoClip,aid);v.status='failed';v.error='Antrean belum tersedia. Coba lagi setelah worker aktif.';s.commit()
def prepare(aid):
    with Session() as s:
        v=lookup(s,aid);v.status='processing';v.error=None;s.commit()
    try:
        root=folder(aid);src=root/'source.media';meta=probe(src);video=next((x for x in meta['streams'] if x['codec_type']=='video'),None);duration=float(meta['format'].get('duration',0))
        if not video or not math.isfinite(duration) or not 0<duration<=settings.library_max_duration:raise RuntimeError(f'Gunakan video valid dengan durasi maksimal {settings.library_max_duration/60:g} menit.')
        run(['ffmpeg','-y','-v','error','-threads','2','-i',str(src),'-an','-vf','scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30','-c:v','libx264','-threads','2','-preset','veryfast','-crf','26','-g','15','-movflags','+faststart',str(root/'proxy.partial.mp4')])
        (root/'proxy.partial.mp4').replace(root/'proxy.mp4');(root/'thumbs').mkdir(exist_ok=True)
        run(['ffmpeg','-y','-v','error','-i',str(root/'proxy.mp4'),'-vf','fps=1,scale=160:-2','-q:v','5',str(root/'thumbs/%05d.jpg')])
        import shutil
        if not (root/'thumbs/00001.jpg').exists():run(['ffmpeg','-y','-v','error','-i',str(root/'proxy.mp4'),'-frames:v','1','-vf','scale=160:-2',str(root/'thumbs/00001.jpg')])
        shutil.copyfile(root/'thumbs/00001.jpg',root/'thumb.jpg')
        metadata={'frames':math.floor(duration*30),'duration':duration,'width':video['width'],'height':video['height']};write_json(root/'metadata.json',metadata)
        with Session() as s:
            v=lookup(s,aid);v.duration=duration;v.width=video['width'];v.height=video['height'];v.status='ready';s.commit()
    except Exception as e:
        with Session() as s:
            v=lookup(s,aid);v.status='failed';v.error=str(e) if isinstance(e,RuntimeError) else 'Video gagal diproses. Periksa file lalu coba lagi.';s.commit()
        raise
