import pytest
from pydantic import ValidationError
from app.schemas import ProjectInput, EditPlan
from app.tasks import words_for_clip
from app.media import ass_time, subtitles, layout_filter

def test_url_canonicalization():
    assert ProjectInput(gemini_model='gemini-test',url='https://youtu.be/dQw4w9WgXcQ?t=12').url=='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
@pytest.mark.parametrize('url',['http://youtube.com/watch?v=dQw4w9WgXcQ','https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ','https://youtube.com/playlist?list=x','https://127.0.0.1/','https://youtube.com:444/watch?v=dQw4w9WgXcQ'])
def test_reject_bad_sources(url):
    with pytest.raises(ValidationError):ProjectInput(gemini_model='gemini-test',url=url)
def test_word_time_conversion():
    words=[{'start':9.8,'end':10.3,'text':'a'},{'start':11,'end':12,'text':'b'},{'start':14,'end':15,'text':'c'}]
    result=words_for_clip(words,10,11.5)
    assert result[0]['start']==0
    assert result[1]['end']==1.5
    assert len(result)==2
@pytest.mark.parametrize('data',[{'start':4,'end':3},{'start':0,'end':5,'layouts':[{'start':1}]},{'start':0,'end':5,'words':[{'start':4,'end':6,'text':'x'}]},{'start':0,'end':5,'layouts':[{'start':0},{'start':4},{'start':3}]}])
def test_invalid_timeline(data):
    with pytest.raises(ValidationError):EditPlan(**data)
def test_subtitle_escape_and_timestamp(tmp_path):
    plan=EditPlan(start=10,end=12,words=[{'start':0,'end':.5,'text':'{\\pos(1,1)}hello'}]).model_dump()
    p=tmp_path/'captions.ass'; subtitles(plan,p)
    assert r'\pos(1,1)' not in p.read_text()
    assert '0:00:00.00,0:00:00.50' in p.read_text()
    assert ass_time(3661.23)=='1:01:01.23'
def test_portrait_crop_scales_before_cropping():
    f=layout_filter({'mode':'a','a':.3,'b':.7},360,640)
    assert f.index('scale=')<f.index('crop=')
