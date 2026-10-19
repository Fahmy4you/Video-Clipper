import json,subprocess
from pathlib import Path
import numpy as np
import pytest
from pydantic import ValidationError
from PIL import Image
from app.timeline import EditPlanV2,VisualStyle,upgrade_plan,RESOLUTIONS
from app.schemas import ProjectInput,Highlights
from app.render_v2 import render_v2
from app.media import probe

def test_project_options_and_limits():
    for n in (1,5):
        p=ProjectInput(url='https://youtu.be/K-iDtHzEzu8',gemini_model='gemini-test',highlight_count=n,aspect_ratio='4:3',additional_prompt='Sekitar 1:32 topik money management, jangan dilewatkan.')
        assert p.highlight_count==n and p.aspect_ratio=='4:3'
    for bad in ({'highlight_count':6},{'aspect_ratio':'3:2'},{'additional_prompt':'x'*4001}):
        with pytest.raises(ValidationError):ProjectInput(url='https://youtu.be/K-iDtHzEzu8',gemini_model='gemini-test',**bad)

def test_legacy_conversion_stable_and_preserves_layouts():
    old={'start':10,'end':14,'words':[{'start':.1,'end':.5,'text':'Halo'},{'start':2.1,'end':2.5,'text':'Dunia'}],'layouts':[{'start':0,'mode':'a','a':.4,'b':.7},{'start':2,'mode':'split','a':.3,'b':.8}],'style':{'font':'DejaVu Sans','size':62,'color':'#FFFFFF','highlight':'#5EEAD4','outline':3,'margin':180}}
    new=upgrade_plan(old,'sample')
    assert new==upgrade_plan(old,'sample')==upgrade_plan(new)
    assert [s['source_in'] for s in new['segments']]==[300,360]
    assert sum(s['duration'] for s in new['segments'])==120
    assert new['segments'][1]['transform']['mode']=='split'
    assert new['segments'][1]['captions'][0]['words'][0]['start']==3
    assert old['start']==10

def test_v2_rejects_canvas_override_and_invalid_timing():
    good={'segments':[{'id':'s','source_in':0,'duration':30}]}
    EditPlanV2.model_validate(good)
    with pytest.raises(ValidationError):EditPlanV2.model_validate({**good,'aspect_ratio':'16:9'})
    with pytest.raises(ValidationError):EditPlanV2.model_validate({'segments':[{'id':'s','source_in':0,'duration':30,'overlays':[{'id':'o','kind':'text','start':10,'end':40}]}]})

def test_unfulfilled_requests_and_five_results_schema():
    value=Highlights(clips=[{'start':i*30,'end':i*30+20,'title':str(i),'reason':'test','fulfills_prompt':i==0} for i in range(5)],unmet_requests=['Topik di 99:00 di luar durasi sumber.'])
    assert len(value.clips)==5 and value.clips[0].fulfills_prompt

@pytest.fixture(scope='module')
def source(tmp_path_factory):
    root=tmp_path_factory.mktemp('visual-render');p=root/'source.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',"color=red:s=160x90:r=30:d=4,drawbox=color=blue:t=fill:enable='gte(t,2)'",'-f','lavfi','-i',r'aevalsrc=sin(2*PI*if(lt(t\,2)\,300\,900)*t):s=48000:d=4','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(p)],check=True)
    return p

@pytest.mark.parametrize('ratio',list(RESOLUTIONS))
def test_render_reordered_video_and_audio_all_ratios(source,ratio):
    plan=EditPlanV2(segments=[{'id':'blue','source_in':60,'duration':15},{'id':'red','source_in':0,'duration':15}]).model_dump()
    out=source.parent/(ratio.replace(':','-')+'.mp4');render_v2(source,plan,out,preview=True,ratio=ratio)
    meta=probe(out);v=next(x for x in meta['streams'] if x['codec_type']=='video')
    w,h=RESOLUTIONS[ratio];assert (v['width'],v['height'])==(round(w/3/2)*2,round(h/3/2)*2)
    assert abs(float(meta['format']['duration'])-1)<1/30+.001
    for t,expected in ((.2,900),(.7,300)):
        data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(out),'-t','0.15','-vn','-ac','1','-ar','8000','-f','f32le','-'])
        samples=np.frombuffer(data,dtype='<f4');frequency=np.fft.rfftfreq(len(samples),1/8000)[np.argmax(abs(np.fft.rfft(samples)))]
        assert abs(frequency-expected)<15
    pixels=subprocess.check_output(['ffmpeg','-v','error','-ss','0.2','-i',str(out),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'])
    assert pixels[2]>pixels[0]

def test_caption_and_transparent_image_composite(source):
    from app.render_v2 import overlay_image
    assets=source.parent/'assets';assets.mkdir(exist_ok=True)
    aid='00000000-0000-0000-0000-000000000001'
    Image.new('RGBA',(10,10),(255,0,0,128)).save(assets/(aid+'.png'))
    plan=EditPlanV2(segments=[{'id':'s','source_in':0,'duration':30,'overlays':[{'id':'i','kind':'image','asset_id':aid,'start':0,'end':15,'style':{'x':.5,'y':.5,'width':.2,'height':.2}}],'captions':[{'id':'c','start':0,'end':30,'words':[{'id':'w','start':0,'end':30,'text':'Subtitle'}]}]}]).model_dump()
    im=overlay_image(plan['segments'][0],plan['subtitle_style'],0,360,640,source.parent)
    assert im.getpixel((180,320))==(255,0,0,128)
    assert overlay_image(plan['segments'][0],plan['subtitle_style'],20,360,640,source.parent).getpixel((180,320))[3]==0

@pytest.mark.parametrize('ratio,mode,scale',[('9:16','fill',1),('16:9','fill',1.11),('4:5','split',1),('1:1','fit',1),('4:3','fill',1)])
def test_full_resolution_fill_and_odd_split_height(source,ratio,mode,scale):
    plan=EditPlanV2(segments=[{'id':'s','source_in':0,'duration':3,'transform':{'mode':mode,'scale':scale}}]).model_dump()
    out=source.parent/(ratio.replace(':','-')+'-'+mode+'.mp4')
    render_v2(source,plan,out,ratio=ratio)
    meta=probe(out);v=next(x for x in meta['streams'] if x['codec_type']=='video')
    assert (v['width'],v['height'])==RESOLUTIONS[ratio]

def test_fit_position_matches_canvas_not_forced_center(source):
    plan=EditPlanV2(segments=[{'id':'s','source_in':0,'duration':3,'transform':{'mode':'fit','y':0}}]).model_dump()
    out=source.parent/'fit-top.mp4';render_v2(source,plan,out,preview=True,ratio='1:1')
    data=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
    pixels=np.frombuffer(data,dtype=np.uint8).reshape(360,360,3)
    assert pixels[10,180,0]>200
    assert max(pixels[350,180])<10
