import json
from pathlib import Path
from copy import deepcopy
import pytest
from app import subtitle_refinement as sr
from app.timeline import EditPlanV2
from app.subtitle_presentation import presentation,change_points

def sample():
    return EditPlanV2(segments=[{'id':'s','source_in':300,'duration':90,'captions':[{'id':'c','start':0,'end':50,'words':[{'id':'w','start':2,'end':30,'text':'mass'}]}],'overlays':[{'id':'o','kind':'text','start':0,'end':30,'text':'Keep'}]}]).model_dump()

def test_review_apply_preserves_other_edits_and_requires_explicit_selection():
    p=sample();ws=[{'start':10.1,'end':10.9,'text':'emas','probability':.7}]
    proposals=sr.review(p,ws)
    assert proposals[0]['before']=='mass' and proposals[0]['after']=='emas'
    unchanged=sr.apply_review(p,proposals,set());assert unchanged==p
    updated=sr.apply_review(p,proposals,{'c'})
    assert updated['segments'][0]['captions'][0]['words'][0]['text']=='emas'
    assert updated['segments'][0]['overlays']==p['segments'][0]['overlays']
    assert p['segments'][0]['captions'][0]['words'][0]['text']=='mass'

def test_review_never_recreates_deleted_subtitle_or_erases_on_silence():
    p=sample();p['segments'][0]['captions']=[]
    assert sr.review(p,[{'start':10.1,'end':10.9,'text':'emas'}])==[]
    assert sr.review(sample(),[])==[]

def test_source_mapping_reordered_and_repeated_cuts():
    p=sample();s=deepcopy(p['segments'][0]);s['id']='copy';p['segments'].insert(0,s)
    proposals=sr.review(p,[{'start':10.1,'end':10.9,'text':'emas','probability':.4}])
    assert [x['frame'] for x in proposals]==[0,90]
    assert all(x['needs_review'] for x in proposals)

@pytest.fixture
def fake(monkeypatch,tmp_path):
    src=tmp_path/'source.mp4';src.write_bytes(b'source');calls=[]
    class Child:
        peak=400000000
        def __init__(self,*a,**kw):assert kw['model']=='small'
        def wait(self,*a):pass
        def transcribe(self,audio,index,language,hotwords):
            calls.append((index,hotwords));return {'language':'id','words':[{'start':2.1,'end':2.7,'text':'emas','probability':.9}]}
        def close(self):pass
    monkeypatch.setattr(sr,'Child',Child);monkeypatch.setattr(sr,'run',lambda args,check:Path(args[-1]).write_bytes(b'audio'))
    return src,calls

def test_range_checkpoint_is_reused_and_invalidates_changed_source(fake):
    src,calls=fake
    a=sr.refine(src,100,[(10,20)],language='id');b=sr.refine(src,100,[(10,20)],language='id')
    assert a['words']==b['words'] and len(calls)==1
    assert a['words'][0]['start']==10.1 and a['words'][0]['probability']==.9
    src.write_bytes(b'changed source');sr.refine(src,100,[(10,20)],language='id');assert len(calls)==2

def test_word_mode_hides_silence_and_zoom_preserves_word_identity():
    c=sample()['segments'][0]['captions'][0];s={'subtitle_mode':'word','subtitle_animation':'soft_zoom'}
    assert presentation(c,s,1)[0]==[]
    assert presentation(c,s,2)[0][0]['text']=='mass'
    assert presentation(c,s,2)[1]==pytest.approx(.9)
    assert presentation(c,s,6)[1]==1
    assert presentation(c,s,29)[1]==pytest.approx(.96)
    assert presentation(c,s,30)[0]==[]
    assert {2,3,4,5,6,25,26,27,28,29,30}<=change_points(c,s)

@pytest.mark.parametrize('length',[1,2,3,4,5,8,30])
def test_short_words_have_no_animation_overlap(length):
    c={'start':0,'end':length,'words':[{'start':0,'end':length,'text':'ya'}]}
    for f in range(length):
        words,scale=presentation(c,{'subtitle_mode':'word','subtitle_animation':'soft_zoom'},f)
        assert len(words)==1 and .9<=scale<=1


def test_apply_endpoint_revision_and_clip_ownership(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base,Project,Clip,Job
    from app.main import apply_subtitles,SubtitleApplyRequest
    from fastapi import HTTPException
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        p=Project(url='https://youtu.be/niXAuUhK-tw');db.add(p);db.flush()
        c=Clip(project_id=p.id,title='Keep title',plan=sample());db.add(c);db.flush()
        proposals=sr.review(c.plan,[{'start':10.1,'end':10.9,'text':'emas','probability':.8}])
        j=Job(project_id=p.id,clip_id=c.id,kind='subtitle_refine',status='succeeded',result={'revision':1,'proposals':proposals});db.add(j);db.commit()
        body=SubtitleApplyRequest(job_id=j.id,revision=2,caption_ids=['c'])
        with pytest.raises(HTTPException) as e:apply_subtitles(c.id,body,db)
        assert e.value.status_code==409 and c.revision==1
        body.revision=1;result=apply_subtitles(c.id,body,db)
        assert result['revision']==2 and result['title']=='Keep title'
        assert result['plan']['segments'][0]['captions'][0]['words'][0]['text']=='emas'
        with pytest.raises(HTTPException) as e:apply_subtitles(c.id,body,db)
        assert e.value.status_code==409
    engine.dispose()

def test_word_render_hides_gaps_and_zoom_changes_only_caption_layer(tmp_path):
    from app.render_v2 import overlay_image
    p=sample();s=p['segments'][0];style=p['subtitle_style'];style.update(subtitle_mode='word',subtitle_animation='soft_zoom')
    s['overlays']=[]
    assert overlay_image(s,style,1,360,640,tmp_path).getbbox() is None
    a=overlay_image(s,style,2,360,640,tmp_path);b=overlay_image(s,style,6,360,640,tmp_path)
    assert a.getbbox() and b.getbbox() and a.tobytes()!=b.tobytes()
    assert overlay_image(s,style,30,360,640,tmp_path).getbbox() is None


def test_failed_child_budget_survives_restart_and_new_job_allows_retry(fake,monkeypatch):
    source,_=fake;calls=[]
    class Failing:
        def __init__(self,*a,**kw):pass
        def wait(self,*a):calls.append(1);raise sr.TranscriptionFailure('memory')
        def close(self):pass
    monkeypatch.setattr(sr,'Child',Failing)
    for _ in range(2):
        with pytest.raises(sr.TranscriptionFailure):sr.refine(source,100,[(10,20)],jid='job-1',language='id')
    assert len(calls)==2
    with pytest.raises(sr.TranscriptionFailure):sr.refine(source,100,[(10,20)],jid='job-2',language='id')
    assert len(calls)==4


def test_new_highlight_uses_small_and_retry_keeps_user_edits(tmp_path,monkeypatch):
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import sessionmaker
    from types import SimpleNamespace
    from app.db import Base,Project,Clip,Job
    from app import tasks
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        project=Project(url='https://youtu.be/niXAuUhK-tw');db.add(project);db.flush()
        job=Job(project_id=project.id,kind='analysis',payload={'subtitle_mode':'word','subtitle_animation':'soft_zoom'});db.add(job);db.commit();pid,jid=project.id,job.id
    (tmp_path/'source.mp4').write_bytes(b'source')
    (tmp_path/'metadata.json').write_text(json.dumps({'title':'Source'}))
    (tmp_path/'transcript.json').write_text(json.dumps({'language':'id','words':[{'start':.1,'end':.8,'text':'mass'}]}))
    monkeypatch.setattr(tasks,'Session',factory);monkeypatch.setattr(tasks,'probe',lambda _: {'streams':[{'codec_type':'audio'}],'format':{'duration':'40'}})
    monkeypatch.setattr(tasks,'update',lambda *a,**kw:None);monkeypatch.setattr(tasks,'check',lambda *a:None)
    monkeypatch.setattr(tasks,'connections',lambda:[True]);monkeypatch.setattr(tasks,'read_checkpoint',lambda *a:None);monkeypatch.setattr(tasks,'checkpoint',lambda *a:None)
    monkeypatch.setattr(tasks,'generate',lambda **kw:SimpleNamespace(text=json.dumps({'clips':[{'start':0,'end':30,'title':'Title','reason':'Context'}]})))
    calls=[]
    def refine(*a,**kw):calls.append(1);return {'words':[{'start':.1,'end':.8,'text':'emas','probability':.9}]}
    monkeypatch.setattr(sr,'refine',refine)
    tasks.analyze(jid,pid,'url',tmp_path,'gemini-test',1)
    with factory() as db:
        clip=db.scalar(select(Clip));assert clip.plan['subtitle_style']['subtitle_mode']=='word'
        assert clip.plan['segments'][0]['captions'][0]['words'][0]['text']=='emas'
        saved=deepcopy(clip.plan);saved['segments'][0]['captions'][0]['words'][0]['text']='Manual correction';clip.plan=saved;clip.revision=2;db.commit();cid=clip.id
    tasks.analyze(jid,pid,'url',tmp_path,'gemini-test',1)
    with factory() as db:
        assert len(list(db.scalars(select(Clip))))==1
        assert db.get(Clip,cid).plan==saved and db.get(Clip,cid).revision==2
        assert db.get(Project,pid).analysis_report['subtitle_model']=='small'
    assert len(calls)==1
    engine.dispose()


def test_vocabulary_hints_follow_source_context_not_every_podcast(tmp_path):
    src=tmp_path/'source.mp4'
    (tmp_path/'transcript.json').write_text(json.dumps({'words':[{'start':1,'end':2,'text':'sekolah'},{'start':300,'end':301,'text':'mining tabang mass'}]}))
    assert sr.context_hotwords(src,0,10) is None
    assert 'emas' in sr.context_hotwords(src,290,310)


def test_child_passes_context_hints_and_keeps_word_confidence(monkeypatch):
    import sys,io,os
    from types import SimpleNamespace
    from app import transcription_child
    calls=[]
    class Model:
        def __init__(self,*a,**kw):assert kw['device']=='cpu' and kw['compute_type']=='int8'
        def transcribe(self,audio,**kw):
            calls.append(kw)
            return [SimpleNamespace(words=[SimpleNamespace(start=0,end=1,word='emas',probability=.8)])],SimpleNamespace(language='id')
    monkeypatch.setenv('VC_PARENT_PID',str(os.getppid()))
    monkeypatch.setattr(transcription_child.ctypes,'CDLL',lambda _:SimpleNamespace(prctl=lambda *a:None))
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps({'audio':'sample.wav','index':0,'language':'id','hotwords':'mining emas, tambang emas'})+'\n'))
    output=io.StringIO();monkeypatch.setattr(sys,'stdout',output)
    transcription_child.main()
    result=json.loads(output.getvalue().splitlines()[-1]);assert result['words'][0]['probability']==.8
    assert calls[0]['hotwords']==calls[0]['initial_prompt']=='mining emas, tambang emas'
    assert calls[0]['word_timestamps'] and calls[0]['vad_filter']


def test_generic_crypto_mining_does_not_force_gold_vocabulary(tmp_path):
    src=tmp_path/'source.mp4'
    (tmp_path/'transcript.json').write_text(json.dumps({'words':[{'start':1,'end':2,'text':'Bitcoin mining'}]}))
    hints=sr.context_hotwords(src,0,10)
    assert 'Bitcoin' in hints and 'emas' not in hints
