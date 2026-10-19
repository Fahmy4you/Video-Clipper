import shutil, subprocess
import pytest
from app.schemas import EditPlan
from app.media import render,probe,run,Cancelled

@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg diperlukan')
def test_real_render_preserves_duration_audio_and_format(tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True)
    plan=EditPlan(start=.2,end=2.8,words=[{'start':.1,'end':1,'text':'Tes subtitle'}],layouts=[{'start':0,'mode':'a'},{'start':1.3,'mode':'split'}]).model_dump()
    out=tmp_path/'preview.mp4';render(source,plan,out,preview=True)
    data=probe(out); video=next(x for x in data['streams'] if x['codec_type']=='video')
    assert (video['width'],video['height'])==(360,640)
    assert video['codec_name']=='h264'
    assert any(x['codec_type']=='audio' for x in data['streams'])
    assert abs(float(data['format']['duration'])-2.6)<.15
def test_cancel_stops_child():
    def check(): raise Cancelled()
    with pytest.raises(Cancelled):run(['sleep','20'],check)
