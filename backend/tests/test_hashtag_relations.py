import pytest
from sqlalchemy import create_engine,event,select,func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db import Base,VideoClip,Hashtag,video_clip_hashtags
from app.hashtag_api import create,rename,remove,TagInput
from app.video_library import edit,Metadata,snapshot

@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    @event.listens_for(engine,'connect')
    def foreign_keys(conn,_):conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as s:yield s
    engine.dispose()

def test_many_to_many_delete_keeps_videos_and_other_tags(db):
    tags=[Hashtag(name_tag=n) for n in ['r','o','p']];db.add_all(tags);db.flush()
    a=VideoClip(title='A',tag_records=tags);b=VideoClip(title='B',tag_records=[tags[1]])
    db.add_all([a,b]);db.commit();ids=[a.id,b.id];old=a.revision
    remove(tags[1].id,db);db.expire_all()
    assert db.get(VideoClip,ids[0]).hashtags==['p','r']
    assert db.get(VideoClip,ids[1]).hashtags==[]
    assert db.get(VideoClip,ids[0]).revision==old+1
    assert db.scalar(select(func.count()).select_from(VideoClip))==2
    assert db.scalar(select(func.count()).select_from(video_clip_hashtags))==2

def test_rename_propagates_and_duplicate_rejected(db):
    tag=create(TagInput(name_tag='#Luxury'),db);v=VideoClip(title='Video',tag_records=[db.get(Hashtag,tag['id'])]);db.add(v);db.commit()
    rename(tag['id'],TagInput(name_tag='Supercar'),db);db.expire_all()
    assert db.get(VideoClip,v.id).hashtags==['supercar']
    with pytest.raises(HTTPException) as exc:create(TagInput(name_tag='#SUPERCAR'),db)
    assert exc.value.status_code==409

def test_attach_detach_and_stale_save(db):
    tag=create(TagInput(name_tag='otomotif'),db);v=VideoClip(title='Video',status='ready',duration=3);db.add(v);db.commit()
    result=edit(v.id,Metadata(title=v.title,revision=v.revision,hashtag_ids=[tag['id']]),db)
    assert result['hashtags']==['otomotif']
    assert len(snapshot(db,['otomotif']))==1
    old=v.revision
    remove(tag['id'],db);db.expire_all()
    with pytest.raises(HTTPException) as exc:edit(v.id,Metadata(title='Video',revision=old,hashtag_ids=[tag['id']]),db)
    assert exc.value.status_code==409
    with pytest.raises(HTTPException) as exc:edit(v.id,Metadata(title='Video',revision=v.revision,hashtag_ids=[tag['id']]),db)
    assert exc.value.status_code==422
    assert snapshot(db,['otomotif'])==[]
    assert len(snapshot(db,[]))==1

def test_detach_only_changes_one_video(db):
    t=Hashtag(name_tag='mobil');a=VideoClip(title='A',tag_records=[t]);b=VideoClip(title='B',tag_records=[t]);db.add_all([a,b]);db.commit()
    edit(a.id,Metadata(title='A',revision=a.revision,hashtag_ids=[]),db);db.expire_all()
    assert a.hashtags==[] and b.hashtags==['mobil']
    assert db.get(Hashtag,t.id) is not None


def test_snapshot_requires_every_selected_tag(db):
    fory=Hashtag(name_tag='fory');asek=Hashtag(name_tag='asek')
    a=VideoClip(title='Both',status='ready',tag_records=[fory,asek])
    b=VideoClip(title='Only fory',status='ready',tag_records=[fory])
    c=VideoClip(title='Only asek',status='ready',tag_records=[asek])
    d=VideoClip(title='No tags',status='ready')
    e=VideoClip(title='Not ready',status='queued',tag_records=[fory,asek])
    db.add_all([a,b,c,d,e]);db.commit()
    assert {x['id'] for x in snapshot(db,[])}=={a.id,b.id,c.id,d.id}
    assert {x['id'] for x in snapshot(db,['fory'])}=={a.id,b.id}
    assert [x['id'] for x in snapshot(db,['fory','asek'])]==[a.id]
    assert snapshot(db,['fory','asek','absent'])==[]
