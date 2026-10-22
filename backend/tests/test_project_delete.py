from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,event,select
from sqlalchemy.orm import Session
from app import main,config
from app.db import Base,Project,Clip,Job,VideoClip,Hashtag

@pytest.fixture
def data(monkeypatch,tmp_path):
    engine=create_engine('sqlite://')
    @event.listens_for(engine,'connect')
    def fk(conn,_):conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine);storage=tmp_path/'storage';(storage/'projects').mkdir(parents=True)
    monkeypatch.setattr(config,'STORAGE',storage)
    with Session(engine,expire_on_commit=False) as s:
        p=Project(id=str(uuid4()),title='Delete fixture',url='https://youtu.be/K-iDtHzEzu8');other=Project(id=str(uuid4()),title='Keep',url=p.url);s.add_all([p,other]);s.flush()
        c=Clip(project_id=p.id,title='Fixture clip',plan={});s.add(c);s.flush()
        job=Job(project_id=p.id,clip_id=c.id,kind='export',status='succeeded');shared=VideoClip(title='Shared library',tag_records=[Hashtag(name_tag='keep')]);s.add_all([job,shared]);s.commit()
        folder=storage/'projects'/p.id;folder.mkdir();(folder/'source.mp4').write_bytes(b'source');(folder/'audio').mkdir();(folder/'audio'/'a.mp3').write_bytes(b'audio');(folder/(job.id+'.mp4')).write_bytes(b'export')
        other_folder=storage/'projects'/other.id;other_folder.mkdir();(other_folder/'keep.mp4').write_bytes(b'keep')
        yield s,p,c,job,folder,other,shared,storage
    engine.dispose()

def test_project_delete_cleans_db_and_only_project_files(data):
    s,p,c,j,folder,other,shared,storage=data
    pid,cid,jid=p.id,c.id,j.id
    result=main.delete_project(pid,s)
    assert result['clip_ids']==[cid] and not result['cleanup_pending']
    assert not folder.exists() and not list((storage/'projects').glob('.delete-*'))
    assert s.get(Project,pid) is None and s.get(Clip,cid) is None and s.get(Job,jid) is None
    assert s.get(Project,other.id) and (storage/'projects'/other.id/'keep.mp4').exists()
    assert s.get(VideoClip,shared.id).hashtags==['keep']

def test_project_delete_busy_rejected(data):
    s,p,c,j,folder,*_=data;j.status='running';s.commit()
    with pytest.raises(HTTPException) as e:main.delete_project(p.id,s)
    assert e.value.status_code==409 and (folder/'source.mp4').exists()
    assert s.get(Clip,c.id)

def test_project_delete_commit_failure_restores_folder(data,monkeypatch):
    s,p,c,j,folder,*_=data
    def fail():raise RuntimeError('database failure')
    monkeypatch.setattr(s,'commit',fail)
    with pytest.raises(RuntimeError):main.delete_project(p.id,s)
    assert (folder/'source.mp4').read_bytes()==b'source' and (folder/'audio'/'a.mp3').exists()
    assert s.get(Project,p.id) and s.get(Clip,c.id)

def test_project_delete_rejects_symlink(data,tmp_path):
    s,p,c,j,folder,*_=data
    main.shutil.rmtree(folder);outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('safe');folder.symlink_to(outside,target_is_directory=True)
    with pytest.raises(HTTPException) as e:main.delete_project(p.id,s)
    assert e.value.status_code==409 and (outside/'keep').read_text()=='safe'
    assert s.get(Project,p.id)

def test_project_delete_reports_filesystem_cleanup_failure(data,monkeypatch):
    s,p,c,j,folder,other,shared,storage=data
    def fail(_):raise OSError('locked files')
    monkeypatch.setattr(main.shutil,'rmtree',fail)
    result=main.delete_project(p.id,s)
    assert result['cleanup_pending'] and not folder.exists() and s.get(Project,p.id) is None
    assert list((storage/'projects').glob('.delete-*'))

def test_project_delete_missing(data):
    with pytest.raises(HTTPException) as e:main.delete_project(str(uuid4()),data[0])
    assert e.value.status_code==404
