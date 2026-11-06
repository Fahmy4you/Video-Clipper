import json
from uuid import uuid4
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,select,event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main,tasks,review,review_build,subtitle_refinement,editor_assets
from app.db import Base,Project,Clip,HighlightProposal,Job,Instansi
from app.schemas import ProjectInput,Highlights
from app.review import ProposalInput,ProposalUpdate,VideoSettings,ApprovalBatch

@pytest.fixture
def data(monkeypatch,tmp_path):
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def keys(c,_):c.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    for m in (tasks,review_build):monkeypatch.setattr(m,'Session',factory)
    monkeypatch.setattr(main,'validate_model',lambda _:None)
    monkeypatch.setattr(main,'wake',lambda:None);monkeypatch.setattr(review,'wake',lambda:None)
    for m in (main,review,review_build):monkeypatch.setattr(m,'project_dir',lambda _:tmp_path)
    monkeypatch.setattr(tasks,'check',lambda _:None);monkeypatch.setattr(tasks,'update',lambda *a,**kw:None)
    monkeypatch.setattr(tasks,'connections',lambda:[object()])
    monkeypatch.setattr(tasks,'read_checkpoint',lambda *a:None);monkeypatch.setattr(tasks,'checkpoint',lambda *a:None)
    with factory() as s:
        p=Project(url='https://youtu.be/K-iDtHzEzu8',gemini_model='gemini-test',duration=600,workflow='review')
        s.add(p);s.commit();pid=p.id
    (tmp_path/'source.mp4').touch();(tmp_path/'metadata.json').write_text('{"title":"Podcast fixture"}')
    words=[{'start':i,'end':i+.8,'text':'Konteks.'} for i in range(600)]
    (tmp_path/'transcript.json').write_text(json.dumps({'words':words,'language':'id'}))
    yield factory,pid,tmp_path
    engine.dispose()

def proposal(s,pid,start=300,end=1500):
    p=HighlightProposal(project_id=pid,title='Usulan',summary='Inti',reason='Alasan',start=start,end=end,original_start=start,original_end=end)
    s.add(p);s.commit();return p

def configure(s,p,ratio='9:16',**kwargs):
    return review.revise(p.id,ProposalUpdate(title=p.title,summary=p.summary,start=p.start,end=p.end,revision=p.revision,settings=VideoSettings(aspect_ratio=ratio,**kwargs)),s)
def approve(s,pid,*rows):
    return review.process(pid,ApprovalBatch(items=[{'id':p.id,'revision':p.revision} for p in rows]),s)

def test_review_analysis_stops_before_video_work(data,monkeypatch):
    factory,pid,folder=data
    forbidden=Mock(side_effect=AssertionError('Video work ran during analysis'))
    monkeypatch.setattr(subtitle_refinement,'refine',forbidden)
    monkeypatch.setattr(editor_assets,'prepare_editor',forbidden)
    monkeypatch.setattr(tasks,'probe',lambda _: {'streams':[{'codec_type':'audio'}],'format':{'duration':'600'}})
    response={'clips':[{'start':10,'end':45,'title':'Nilai isi','summary':'Pesan utama','reason':'Konteks utuh'},
        {'start':50,'end':79,'title':'Terlalu pendek','reason':'Tidak valid'},
        {'start':100,'end':190,'title':'Pembahasan utuh','reason':'Selesai'}]}
    generate=Mock(return_value=type('Response',(),{'text':json.dumps(response)})());monkeypatch.setattr(tasks,'generate',generate)
    tasks.analyze('job',pid,'unused',folder,'gemini-test',3,'','review')
    with factory() as s:
        rows=list(s.scalars(select(HighlightProposal)));assert len(rows)==2
        assert not list(s.scalars(select(Clip)))
        assert not list(s.scalars(select(Job)))
        assert s.get(Project,pid).status=='review'
        assert rows[0].summary=='Pesan utama'
    forbidden.assert_not_called();assert generate.call_count==1
    assert 'finansial' not in generate.call_args.kwargs['contents']
    # Resume does not replace a reviewed range.
    with factory() as s:
        p=s.scalar(select(HighlightProposal));p.start=0;s.commit()
    tasks.analyze('job',pid,'unused',folder,'gemini-test',3,'','review')
    with factory() as s:assert s.scalar(select(HighlightProposal)).start==0

def test_manual_range_beyond_90_and_frame_bounds(data):
    factory,pid,_=data
    with factory() as s:
        p=proposal(s,pid)
        result=review.revise(p.id,ProposalUpdate(title='Revisi',start=0,end=18000,revision=1),s)
        assert result['end']==18000 and result['revision']==2 and result['original_start']==300
        for start,end in [(0,29),(-1,90),(60,30),(0,18001)]:
            with pytest.raises(Exception):review.validate_range(start,end,600)
        with pytest.raises(HTTPException) as e:review.revise(p.id,ProposalUpdate(title='Stale',start=0,end=300,revision=1),s)
        assert e.value.status_code==409
        assert review.transcript_range(pid,0,18000,0,2,s)['total']>2

def test_approval_is_atomic_idempotent_and_per_highlight(data):
    factory,pid,_=data
    with factory() as s:
        a=proposal(s,pid);b=proposal(s,pid,2000,5000)
        configure(s,a,'4:3')
        with pytest.raises(HTTPException):approve(s,pid,a,b)
        assert not list(s.scalars(select(Job)))
        configure(s,b,'16:9',visual_mode='mix',mix_hashtags=['nothing'])
        first=approve(s,pid,a,b);again=approve(s,pid,a,b)
        assert [x['id'] for x in first]==[x['id'] for x in again]
        jobs=list(s.scalars(select(Job)));assert len(jobs)==2
        assert {j.payload['aspect_ratio'] for j in jobs}=={'4:3','16:9'}
        assert jobs[1].payload['library']==[]
        assert review.counts(s,pid)['processing']==2
        with pytest.raises(HTTPException):configure(s,a)
        j=s.get(Job,a.job_id);j.status='cancelling';s.commit()
        with pytest.raises(HTTPException):configure(s,a)
        j.status='cancelled';s.commit();configure(s,a,'1:1')
        assert approve(s,pid,a)[0]['payload']['aspect_ratio']=='1:1'
        with pytest.raises(HTTPException):main.retry(j.id,s)

def test_build_preserves_approved_bounds_and_reuses_partial(data,monkeypatch):
    factory,pid,folder=data
    words=json.loads((folder/'transcript.json').read_text())['words']
    refine=Mock(return_value={'words':words,'model':'small'});prepare=Mock()
    monkeypatch.setattr(subtitle_refinement,'refine',refine)
    monkeypatch.setattr(editor_assets,'prepare_editor',prepare)
    from app import mix_generation
    mix=Mock();monkeypatch.setattr(mix_generation,'generate_mix',mix)
    with factory() as s:
        p=proposal(s,pid,317,4627);configure(s,p,'4:3')
        jid=approve(s,pid,p)[0]['id'];payload=s.get(Job,jid).payload
        s.get(Job,jid).status='running';s.commit()
    result=review_build.build(jid,pid,payload,lambda:None)
    review_build.build(jid,pid,payload,lambda:None)
    with factory() as s:
        rows=list(s.scalars(select(Clip)));assert len(rows)==1
        c=rows[0];assert c.id==result['clip_id'] and c.ready and c.aspect_ratio=='4:3'
        assert c.plan['segments'][0]['source_in']==317
        assert c.plan['segments'][0]['duration']==4310
        assert review.state(s,s.get(HighlightProposal,p.id))=='ready'
    mix.assert_not_called();assert prepare.call_count==2

def test_instansi_pivots_prevent_delete_and_count_distinct_projects(data):
    from app.instansi_api import view,remove
    factory,pid,_=data
    with factory() as s:
        owner=Instansi(name='Owner',name_key='owner');s.add(owner);s.commit()
        a=proposal(s,pid);b=proposal(s,pid)
        configure(s,a,visual_mode='mix',instansi_ids=[owner.id]);configure(s,b,visual_mode='mix',instansi_ids=[owner.id])
        assert view(s,owner)['project_count']==1
        with pytest.raises(HTTPException):remove(owner.id,s)
        review.remove(a.id,s);assert s.get(HighlightProposal,b.id)
        assert view(s,owner)['project_count']==1

def test_podcast_normalizes_mix_settings():
    settings=VideoSettings(visual_mode='podcast',instansi_ids=[uuid4()],include_global=False,mix_hashtags=['hello'])
    assert settings.instansi_ids==[] and settings.mix_hashtags==[] and settings.include_global

def test_changed_draft_discards_partial_and_stale_retry(data):
    factory,pid,_=data
    with factory() as s:
        p=proposal(s,pid);configure(s,p)
        jid=approve(s,pid,p)[0]['id'];j=s.get(Job,jid)
        c=Clip(project_id=pid,title='Partial',plan={},ready=False);s.add(c);s.flush()
        p.clip_id=c.id;j.clip_id=c.id;j.status='failed';j.checkpoint={'old-stage':'done'};s.commit()
        old_id=c.id
        review.revise(p.id,ProposalUpdate(title='Different',start=0,end=4000,revision=p.revision),s)
        fresh=approve(s,pid,p)[0]
        assert fresh['payload']['start']==0 and fresh['payload']['end']==4000
        assert s.get(Job,fresh['id']).checkpoint=={}
        assert s.get(Clip,old_id) is None
        assert s.get(Job,jid).clip_id is None

def test_same_revision_retry_keeps_checkpoint(data):
    factory,pid,_=data
    with factory() as s:
        p=proposal(s,pid);configure(s,p)
        jid=approve(s,pid,p)[0]['id'];j=s.get(Job,jid);j.status='failed';j.checkpoint={'valid-stage':123};s.commit()
        result=main.retry(jid,s)
        assert result['id']!=jid and s.get(Job,result['id']).checkpoint=={'valid-stage':123}
        assert p.job_id==result['id']

def test_migration_preserves_existing_plan_and_copies_settings():
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    engine=create_engine('sqlite://')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, aspect_ratio VARCHAR(8),visual_mode VARCHAR(16),subtitle_mode VARCHAR(16),subtitle_animation VARCHAR(16),include_global BOOLEAN,mix_hashtags JSON)'))
        c.execute(text('CREATE TABLE clips (id VARCHAR(36) PRIMARY KEY,project_id VARCHAR(36),plan JSON)'))
        c.execute(text('CREATE TABLE instansi (id VARCHAR(36) PRIMARY KEY)'))
        c.execute(text('CREATE TABLE project_instansi (project_id VARCHAR(36),instansi_id VARCHAR(36))'))
        c.execute(text("INSERT INTO projects VALUES ('p','4:3','mix','word','soft_zoom',0,'[]')"))
        c.execute(text("INSERT INTO clips VALUES ('c','p',:plan)"),{'plan':json.dumps({'unchanged':True})})
        c.execute(text("INSERT INTO instansi VALUES ('owner')"))
        c.execute(text("INSERT INTO project_instansi VALUES ('p','owner')"))
        spec=importlib.util.spec_from_file_location('review_migration','backend/migrations/versions/0013_review_workflow.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.op=Operations(MigrationContext.configure(c));module.upgrade()
        row=c.execute(text('SELECT * FROM clips')).mappings().one()
        assert json.loads(row['plan'])=={'unchanged':True}
        assert row['aspect_ratio']=='4:3' and json.loads(row['processing_config'])['subtitle_mode']=='word'
        assert c.execute(text('SELECT * FROM clip_instansi')).one()==('c','owner')
        assert c.execute(text('SELECT workflow FROM projects')).scalar()=='legacy'
    engine.dispose()

def test_clip_ratio_drives_export_and_subtitle_api_still_works(data,monkeypatch):
    from app import export_delivery
    monkeypatch.setattr(export_delivery,'config_snapshot',lambda:{'mode':'global'})
    from app.schemas import EditPlan,ClipUpdate
    from app.timeline import upgrade_plan
    from app.export_options import ExportRequest,dimensions
    factory,pid,_=data
    with factory() as s:
        plan=upgrade_plan(EditPlan(start=0,end=2,words=[]).model_dump())
        for ratio in ('9:16','16:9','1:1','4:5','4:3'):
            c=Clip(project_id=pid,title=ratio,plan=plan,aspect_ratio=ratio);s.add(c);s.commit()
            job=main.export(c.id,ExportRequest(resolution=360),s)
            assert job['payload']['aspect_ratio']==ratio
            assert (job['payload']['width'],job['payload']['height'])==dimensions(ratio,360)
            s.get(Job,job['id']).status='succeeded';s.commit()
            with pytest.raises(HTTPException) as exc:main.save_clip(c.id,ClipUpdate(title=ratio,plan=plan,revision=c.revision,aspect_ratio='16:9' if ratio!='16:9' else '9:16'),s)
            assert exc.value.status_code==422
        result=main.refine_subtitles(c.id,main.SubtitleRefineRequest(revision=c.revision),s)
        assert result['kind']=='subtitle_refine'

def test_analysis_coexists_with_manual_draft_and_keeps_deletions(data,monkeypatch):
    factory,pid,folder=data
    with factory() as s:
        manual=proposal(s,pid,0,60);manual_id=manual.id
    monkeypatch.setattr(tasks,'probe',lambda _: {'streams':[{'codec_type':'audio'}],'format':{'duration':'600'}})
    monkeypatch.setattr(tasks,'generate',lambda **kw:type('Response',(),{'text':json.dumps({'clips':[{'start':60,'end':95,'title':'AI proposal','reason':'Utuh'}]})})())
    tasks.analyze('job',pid,'unused',folder,'gemini-test',1,'','review')
    with factory() as s:
        assert len(list(s.scalars(select(HighlightProposal))))==2 and s.get(HighlightProposal,manual_id)
        ai=s.scalar(select(HighlightProposal).where(HighlightProposal.id!=manual_id));s.delete(ai);s.commit()
    tasks.analyze('job',pid,'unused',folder,'gemini-test',1,'','review')
    with factory() as s:assert len(list(s.scalars(select(HighlightProposal))))==1
