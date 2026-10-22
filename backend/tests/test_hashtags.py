import pytest
from pydantic import ValidationError
from app.hashtags import normalize_tags,filter_library
from app.schemas import ProjectInput
from app.video_library import Metadata

def test_normalize_and_dedupe():
    assert normalize_tags(['#Luxury','luxury',' #Mobil-Sport ','#日本'])==['luxury','mobil_sport','日本']

@pytest.mark.parametrize('tags',[['bad tag'],['#'],['x'*51],['ok']*31])
def test_api_rejects_invalid_tags(tags):
    with pytest.raises(ValidationError):Metadata(title='Test',hashtags=tags,revision=1)

def test_optional_and_filter_never_falls_back():
    assets=[{'id':'a','hashtags':['fory','asek','luxury']},{'id':'b','hashtags':['fory']},{'id':'c','hashtags':['asek']},{'id':'d','hashtags':[]}]
    assert filter_library(assets,[])==assets
    assert [a['id'] for a in filter_library(assets,['fory'])]==['a','b']
    assert [a['id'] for a in filter_library(assets,['fory','asek'])]==['a']
    assert [a['id'] for a in filter_library(assets,['fory','asek','luxury'])]==['a']
    assert filter_library(assets,['fory','asek','absent'])==[]
    assert filter_library([{'id':'missing_tags'}],['fory'])==[]
    assert [a['id'] for a in filter_library(assets,['fory','fory','asek'])]==['a']

def test_project_tags_canonical_and_default():
    args=dict(url='https://youtu.be/K-iDtHzEzu8',gemini_model='gemini-test')
    assert ProjectInput(**args).mix_hashtags==[]
    assert ProjectInput(**args,visual_mode='mix',mix_hashtags=['#Luxury']).mix_hashtags==['luxury']
