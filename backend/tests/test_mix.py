import json,subprocess
from copy import deepcopy
from uuid import uuid4
import numpy as np
import pytest
from pydantic import ValidationError
from app.timeline import EditPlanV2,RESOLUTIONS
from app.schemas import ProjectInput
from app.mix_generation import validate_suggestions
from app.mix_render import fade_expr,limits
from app.render_v2 import render_v2
from app.media import probe

def plan(duration=600):return EditPlanV2(segments=[{'id':'s','source_in':0,'duration':duration}]).model_dump()
def test_defaults_and_overlap():
    assert ProjectInput(url='https://youtu.be/K-iDtHzEzu8',gemini_model='gemini-test').visual_mode=='podcast'
    p=plan();assert p['source_fade']['in_frames']==0
    a={'id':'b','asset_id':str(uuid4()),'start':60,'end':150}
    p['segments'][0]['broll']=[a,{**a,'id':'c','start':120}]
    with pytest.raises(ValidationError):EditPlanV2.model_validate(p)
    p['segments'][0]['broll']=[{**a,'asset_id':'../escape'}]
    with pytest.raises(ValidationError):EditPlanV2.model_validate(p)

def test_auto_selection_rules():
    ids=[str(uuid4()) for _ in range(5)];assets=[{'id':i,'frames':900} for i in ids]
    candidates=[{'asset_id':ids[0],'start':60,'end':150,'reason':'POV','source_in':300},{'asset_id':ids[0],'start':240,'end':300,'reason':'repeat'},{'asset_id':ids[1],'start':250,'end':340,'reason':'relevant'},{'asset_id':ids[2],'start':450,'end':510,'reason':'over budget'},{'asset_id':ids[3],'start':550,'end':600,'reason':'end'}]
    result=validate_suggestions(plan(),candidates,assets);b=result['segments'][0]['broll'];assert len(b)==2
    assert sum(x['end']-x['start'] for x in b)==180
    assert b[0]['source_in']==300 and b[1]['start']-b[0]['end']>=90
    assert not validate_suggestions(plan(),candidates,[])['segments'][0]['broll']

def test_handles_and_short_transition():
    b={'id':'a','start':90,'end':94,'source_in':0,'transition_in':{'kind':'crossfade','frames':9},'transition_out':{'kind':'black','frames':9}}
    assert limits(b,[b],300,300)==[('black',2),('black',2)]
    b['source_in']=30;assert limits(b,[b],300,300)[0]==('crossfade',2)

def test_fade_expression_offset():
    f={'in_frames':60,'out_frames':60,'span':180,'offset':90}
    expression=fade_expr(f,90);assert 't*30+90' in expression and '180-' in expression
    assert fade_expr({},90)=='1'

@pytest.fixture(scope='module')
def fixture(tmp_path_factory):
    root=tmp_path_factory.mktemp('mix');source=root/'source.mp4';footage=root/'footage';footage.mkdir();aid=str(uuid4())
    for out,color,freq in [(source,'red',300),(footage/'source.media','blue',1200)]:
        subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=30:d=4','-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000:duration=4','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-f','mp4',str(out)],check=True)
    (footage/'metadata.json').write_text(json.dumps({'frames':120}))
    return source,footage,aid

def pixel(out,frame):
    data=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-vf',f'select=eq(n\\,{frame}),scale=1:1','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']);return list(data)
def samples(out,start,duration=.1):
    data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(start),'-i',str(out),'-t',str(duration),'-vn','-ac','1','-ar','8000','-f','f32le','-']);return np.frombuffer(data,dtype='<f4')

@pytest.mark.parametrize('ratio',list(RESOLUTIONS))
def test_mix_render_all_ratios_muted_footage_and_fade(fixture,monkeypatch,ratio):
    source,footage,aid=fixture;monkeypatch.setattr('app.mix_render.folder',lambda _:footage)
    p=plan(120);s=p['segments'][0];s['transform']['mode']='fill';s['broll']=[{'id':'b','asset_id':aid,'start':30,'end':90,'source_in':15}];p['source_fade']={'in_frames':30,'out_frames':30}
    out=source.parent/(ratio.replace(':','-')+'mix.mp4');render_v2(source,p,out,preview=True,ratio=ratio)
    meta=probe(out);assert abs(float(meta['format']['duration'])-4)<1/30
    video=next(x for x in meta['streams'] if x['codec_type']=='video');audio_meta=next(x for x in meta['streams'] if x['codec_type']=='audio');assert int(video['nb_frames'])==120;assert abs(float(audio_meta['duration'])-4)<.001
    rgb=pixel(out,60);assert rgb[2]>200 and rgb[0]<25
    rgb=pixel(out,15);assert rgb[0]>200 and rgb[2]<25
    # Black dip centered at cut, not a duration-increasing transition.
    assert max(pixel(out,30))<25
    audio=samples(out,1.5,.3);frequency=np.fft.rfftfreq(len(audio),1/8000)[np.argmax(abs(np.fft.rfft(audio)))];assert abs(frequency-300)<5
    rms=lambda x:np.sqrt(np.mean(x*x));assert rms(samples(out,.05))<rms(samples(out,.7))*.3
    assert rms(samples(out,3.85))<rms(samples(out,2))*.3

def test_transition_crosses_podcast_segment_boundary(fixture,monkeypatch):
    source,footage,aid=fixture;monkeypatch.setattr('app.mix_render.folder',lambda _:footage)
    p=EditPlanV2(segments=[{'id':'a','source_in':0,'duration':30},{'id':'b','source_in':30,'duration':60,'broll':[{'id':'clip','asset_id':aid,'start':0,'end':60,'source_in':15}]},{'id':'c','source_in':90,'duration':30}]).model_dump()
    out=source.parent/'boundary.mp4';render_v2(source,p,out,preview=True,ratio='16:9');assert max(pixel(out,30))<25;assert pixel(out,60)[2]>200

def test_library_snapshot_json_serializable():
    from app.db import VideoClip
    from app.video_library import info
    from datetime import datetime,timezone
    asset=VideoClip(id=str(uuid4()),title='Test',url_path='managed/source.media',tag_records=[],explain='',scenes=[],duration=8,width=320,height=180,status='ready',archived=False,revision=1,created_at=datetime.now(timezone.utc))
    result=json.loads(json.dumps(info(asset)));assert result['frames']==240

def test_crossfade_overlay_and_split_audio_fade(fixture,monkeypatch):
    source,footage,aid=fixture;monkeypatch.setattr('app.mix_render.folder',lambda _:footage)
    from PIL import Image
    imgid=str(uuid4());(source.parent/'assets').mkdir(exist_ok=True);Image.new('RGBA',(10,10),(0,255,0,255)).save(source.parent/'assets'/f'{imgid}.png')
    (source.parent/'audio').mkdir(exist_ok=True);audioid=str(uuid4());subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-vn','-c:a','copy',str(source.parent/'audio'/f'{audioid}.m4a')],check=True)
    p=plan(120);p['source_volume']=0;s=p['segments'][0];s['transform']['mode']='fill'
    s['broll']=[{'id':'cross','asset_id':aid,'start':30,'end':90,'source_in':15,'transition_in':{'kind':'crossfade','frames':12},'transition_out':{'kind':'crossfade','frames':12}}]
    s['overlays']=[{'id':'image','kind':'image','asset_id':imgid,'start':0,'end':120,'style':{'width':.2,'height':.2,'x':.5,'y':.5}}]
    s['audio']=[{'id':'a','asset_id':audioid,'start':0,'end':30,'source_in':0,'volume':1,'fade':{'in_frames':60,'out_frames':30,'span':120}}, {'id':'b','asset_id':audioid,'start':30,'end':120,'source_in':30,'volume':1,'fade':{'in_frames':60,'out_frames':30,'span':120,'offset':30}}]
    out=source.parent/'crossfade-audio.mp4';render_v2(source,p,out,preview=True,ratio='16:9')
    data=subprocess.check_output(['ffmpeg','-v','error','-ss','1','-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']);pixels=np.frombuffer(data,dtype=np.uint8).reshape(360,640,3)
    assert pixels[180,320,1]>230 # overlay does not fade with base
    assert 85<pixels[30,30,0]<180 and 85<pixels[30,30,2]<180 # crossfade midpoint
    rms=lambda t:float(np.sqrt(np.mean(samples(out,t,.08)**2)))
    assert rms(1.02)>rms(.8) and rms(.05)<rms(1.7)*.15
    assert rms(3.85)<rms(2.5)*.3

def test_automatic_ranges_respect_curated_scenes():
    aid=str(uuid4());assets=[{'id':aid,'frames':900,'scenes':[{'start':300,'end':450,'explain':'POV'}]}]
    candidate={'asset_id':aid,'start':90,'end':180,'source_in':0,'reason':'POV'}
    assert not validate_suggestions(plan(),[candidate],assets)['segments'][0]['broll']
    candidate['source_in']=330
    assert validate_suggestions(plan(),[candidate],assets)['segments'][0]['broll'][0]['source_in']==330


def test_retry_discards_old_or_cache_when_and_filter_has_no_match(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base,Project,Clip,Job
    from app import mix_generation
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(mix_generation,'Session',factory)
    # No Gemini call is allowed when every snapshot candidate fails the AND filter.
    from google import genai
    def forbidden(*args,**kwargs):raise AssertionError('Unfiltered fallback attempted')
    monkeypatch.setattr(genai,'Client',forbidden)
    with factory() as db:
        p=Project(url='https://youtu.be/test',visual_mode='mix');db.add(p);db.flush()
        c=Clip(project_id=p.id,title='Test',plan=plan());db.add(c);db.flush()
        aid=str(uuid4());old=validate_suggestions(plan(),[{'asset_id':aid,'start':90,'end':180,'source_in':0,'reason':'Old OR match'}],[{'id':aid,'frames':300}])
        payload={'library':[{'id':aid,'frames':300,'hashtags':['fory']}],'mix_hashtags':['fory','asek'],'mix_target_ids':[c.id],'mix_results':{c.id:old}}
        job=Job(project_id=p.id,kind='mix',payload=payload);db.add(job);db.commit();pid,cid,jid=p.id,c.id,job.id
    mix_generation.generate_mix(jid,pid,payload,lambda:None)
    with factory() as db:
        saved=db.get(Clip,cid)
        assert saved.revision==2 and not saved.plan['segments'][0]['broll']
        assert not db.get(Job,jid).payload['mix_results'][cid]['segments'][0]['broll']
        assert db.get(Project,pid).analysis_report['mix_status']=='ready'
    engine.dispose()
