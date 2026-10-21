from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,field_validator,ConfigDict
from sqlalchemy import select,func,update
from sqlalchemy.exc import IntegrityError
from .db import session,Hashtag,VideoClip,video_clip_hashtags
from .hashtags import normalize_tags
router=APIRouter(prefix='/api/hashtags')
class TagInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name_tag:str=Field(min_length=1,max_length=60)
    @field_validator('name_tag')
    @classmethod
    def normalize(cls,v):return normalize_tags([v])[0]
class TagView(BaseModel):
    id:str
    name_tag:str
    video_count:int=0

def view(s,tag):
    count=s.scalar(select(func.count()).select_from(video_clip_hashtags).where(video_clip_hashtags.c.hashtag_id==tag.id))
    return {'id':tag.id,'name_tag':tag.name_tag,'video_count':count}
def commit(s):
    try:s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,'Nama hashtag sudah digunakan.')
def lookup(s,id):
    tag=s.scalar(select(Hashtag).where(Hashtag.id==id).with_for_update())
    if not tag:raise HTTPException(404,'Hashtag tidak ditemukan. Muat ulang daftar.')
    return tag
def touch_clips(s,id):
    ids=select(video_clip_hashtags.c.video_clip_id).where(video_clip_hashtags.c.hashtag_id==id)
    s.execute(update(VideoClip).where(VideoClip.id.in_(ids)).values(revision=VideoClip.revision+1))
@router.get('',response_model=list[TagView])
def listing(s=Depends(session)):
    rows=s.execute(select(Hashtag.id,Hashtag.name_tag,func.count(video_clip_hashtags.c.video_clip_id).label('video_count')).outerjoin(video_clip_hashtags,Hashtag.id==video_clip_hashtags.c.hashtag_id).group_by(Hashtag.id,Hashtag.name_tag).order_by(Hashtag.name_tag))
    return [dict(row._mapping) for row in rows]
@router.post('',response_model=TagView,status_code=201)
def create(body:TagInput,s=Depends(session)):
    tag=Hashtag(name_tag=body.name_tag);s.add(tag);commit(s);return view(s,tag)
@router.patch('/{id}',response_model=TagView)
def rename(id:str,body:TagInput,s=Depends(session)):
    tag=lookup(s,id)
    if tag.name_tag!=body.name_tag:touch_clips(s,id);tag.name_tag=body.name_tag
    commit(s);return view(s,tag)
@router.delete('/{id}')
def remove(id:str,s=Depends(session)):
    tag=lookup(s,id);touch_clips(s,id);s.delete(tag);s.commit()
    return {'deleted':id}
