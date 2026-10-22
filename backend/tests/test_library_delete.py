from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,event,select,func
from sqlalchemy.orm import Session
from app import video_library as library
from app.db import Base,Project,Clip,Job,VideoClip,Hashtag,video_clip_hashtags

@pytest.fixture
def data(monkeypatch,tmp_path):
    engine=create_engine('sqlite://')
    @event.listens_for(engine,'connect')
    def fk(conn,_):conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine);storage=tmp_path/'storage';(storage/'video-clips').mkdir(parents=True)
    monkeypatch.setattr(library,'STORAGE',storage)
    with Session(engine,expire_on_commit=False) as s:
        tag=Hashtag(name_tag='keep');asset=VideoClip(title='Delete fixture',status='ready',tag_records=[tag]);other=VideoClip(title='Keep fixture',status='ready',tag_records=[tag]);project=Project(url='https://youtu.be/K-iDtHzEzu8')
        s.add_all([asset,other,project]);s.flush();asset.url_path=f'video-clips/{asset.id}/named-source.mp4';s.commit()
        root=library.folder(asset.id);root.mkdir();(root/'source.media').write_bytes(b'source');(root/'named-source.mp4').write_bytes(b'named source');(root/'proxy.mp4').write_bytes(b'proxy');(root/'thumbs').mkdir();(root/'thumbs/00001.jpg').write_bytes(b'thumb')
        keep=library.folder(other.id);keep.mkdir();(keep/'source.media').write_bytes(b'keep')
        yield s,asset,other,tag,project,root,storage
    engine.dispose()

def plan(aid):return {'segments':[{'broll':[{'asset_id':aid}]}]}

def test_delete_removes_db_pivot_and_all_owned_media_only(data):
    s,v,other,tag,p,root,storage=data;aid=v.id
    result=library.remove(aid,s)
    assert result=={'deleted':aid,'cleanup_pending':False}
    assert s.get(VideoClip,aid) is None and not root.exists()
    assert s.get(Hashtag,tag.id) and s.get(VideoClip,other.id).hashtags==['keep']
    assert s.scalar(select(func.count()).select_from(video_clip_hashtags))==1
    assert (library.folder(other.id)/'source.media').read_bytes()==b'keep'
    assert not list(root.parent.glob('.delete-*'))

@pytest.mark.parametrize('legacy',[False,True])
def test_referenced_video_rejected_without_touching_media(data,legacy):
    s,v,other,tag,p,root,_=data
    c=Clip(project_id=p.id,title='Highlight uses source',plan={} if legacy else plan(v.id),legacy_plan=plan(v.id) if legacy else None);s.add(c);s.commit()
    with pytest.raises(HTTPException) as exc:library.remove(v.id,s)
    assert exc.value.status_code==409 and 'Highlight uses source' in exc.value.detail
    assert s.get(VideoClip,v.id) and (root/'source.media').exists()

@pytest.mark.parametrize('status',['queued','processing'])
def test_processing_asset_rejected(data,status):
    s,v,*_=data;v.status=status;s.commit()
    with pytest.raises(HTTPException) as exc:library.remove(v.id,s)
    assert exc.value.status_code==409 and library.folder(v.id).exists()

@pytest.mark.parametrize('status',['queued','running'])
@pytest.mark.parametrize('payload_kind',['library','plan','mix_results'])
def test_active_job_references_rejected(data,status,payload_kind):
    s,v,other,tag,p,root,_=data
    payload={'library':[{'id':v.id}]} if payload_kind=='library' else {'plan':plan(v.id)} if payload_kind=='plan' else {'mix_results':{'clip':plan(v.id)}}
    s.add(Job(project_id=p.id,kind='analysis',status=status,payload=payload));s.commit()
    with pytest.raises(HTTPException) as exc:library.remove(v.id,s)
    assert exc.value.status_code==409 and root.exists()

@pytest.mark.parametrize('archived,status',[(True,'ready'),(False,'failed')])
def test_archived_or_failed_asset_can_be_permanently_deleted(data,archived,status):
    s,v,*_=data;aid=v.id;v.archived=archived;v.status=status;s.commit()
    assert library.remove(aid,s)['deleted']==aid
    assert s.get(VideoClip,aid) is None

def test_commit_failure_restores_files_and_relations(data,monkeypatch):
    s,v,other,tag,p,root,_=data;aid=v.id
    def fail():raise RuntimeError('database failure')
    monkeypatch.setattr(s,'commit',fail)
    with pytest.raises(RuntimeError):library.remove(aid,s)
    assert (root/'source.media').read_bytes()==b'source'
    assert s.get(VideoClip,aid).hashtags==['keep']
    assert not list(root.parent.glob('.delete-*'))

def test_filesystem_rename_failure_keeps_database(data,monkeypatch):
    s,v,other,tag,p,root,_=data;aid=v.id
    def fail(*args):raise OSError('locked folder')
    monkeypatch.setattr(type(root),'rename',fail)
    with pytest.raises(OSError):library.remove(aid,s)
    assert s.get(VideoClip,aid) and (root/'source.media').exists()

def test_symlink_cannot_delete_outside_storage(data,tmp_path):
    s,v,other,tag,p,root,_=data
    library.shutil.rmtree(root);outside=tmp_path/'originals';outside.mkdir();(outside/'keep').write_text('original')
    root.symlink_to(outside,target_is_directory=True)
    with pytest.raises(HTTPException) as exc:library.remove(v.id,s)
    assert exc.value.status_code==409 and (outside/'keep').read_text()=='original'
    assert s.get(VideoClip,v.id)

def test_missing_folder_still_removes_row(data):
    s,v,other,tag,p,root,_=data;aid=v.id;library.shutil.rmtree(root)
    assert library.remove(aid,s)=={'deleted':aid,'cleanup_pending':False}
    assert s.get(VideoClip,aid) is None

def test_cleanup_failure_reported_instead_of_archiving(data,monkeypatch):
    s,v,other,tag,p,root,_=data;aid=v.id
    def fail(*args):raise OSError('locked media')
    monkeypatch.setattr(library.shutil,'rmtree',fail)
    result=library.remove(aid,s)
    assert result['cleanup_pending'] and s.get(VideoClip,aid) is None
    assert list(root.parent.glob('.delete-*'))

def test_nonexistent_asset_returns_404(data):
    with pytest.raises(HTTPException) as exc:library.remove(str(uuid4()),data[0])
    assert exc.value.status_code==404

def test_old_retry_snapshot_drops_deleted_candidates_and_stale_cache(data):
    s,v,other,*_=data;gone=str(uuid4());keep=plan(v.id)
    original={'library':[{'id':v.id},{'id':gone}], 'mix_results':{'keep':keep,'stale':plan(gone)},'gemini_model':'test','mix_hashtags':['keep']}
    updated=library.live_job_payload(s,original)
    assert updated['library']==[{'id':v.id}] and updated['mix_results']=={'keep':keep}
    assert updated['gemini_model']=='test' and updated['mix_hashtags']==['keep']
    assert len(original['library'])==2

def test_stale_plan_cannot_be_saved_or_enqueued(data):
    with pytest.raises(HTTPException) as exc:library.lock_plan_assets(data[0],plan(str(uuid4())))
    assert exc.value.status_code==409
    library.lock_plan_assets(data[0],plan(data[1].id))
