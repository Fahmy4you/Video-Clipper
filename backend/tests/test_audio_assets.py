import json,subprocess
from pathlib import Path
from uuid import uuid4
import pytest
import numpy as np
from pydantic import ValidationError
from app.audio_assets import AudioImport,normalize_audio,audio_metadata,import_audio
from app.timeline import EditPlanV2
from app.render_v2 import render_v2
from app.main import validate_plan
from fastapi import HTTPException
from types import SimpleNamespace

@pytest.mark.parametrize('platform,url',[('youtube','https://youtu.be/K-iDtHzEzu8'),('tiktok','https://www.tiktok.com/@creator/video/1234567890123456789'),('tiktok','https://vm.tiktok.com/AbC123/')])
def test_supported_audio_urls(platform,url):
    assert AudioImport(platform=platform,url=url).url.startswith('https://')

@pytest.mark.parametrize('url',['http://www.tiktok.com/@x/video/123','https://127.0.0.1/a','https://www.tiktok.com.evil.example/@x/video/123','https://user:pass@www.tiktok.com/@x/video/123','https://www.tiktok.com/@profile'])
def test_reject_unrelated_audio_urls(url):
    with pytest.raises(ValidationError):AudioImport(platform='tiktok',url=url)

@pytest.fixture
def media(tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=30:d=2','-f','lavfi','-i','sine=frequency=730:duration=2','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    return source

def test_extract_video_normalize_and_mix_timed_audio(media):
    aid=str(uuid4());asset=normalize_audio(media,media.parent,aid,'Test video','upload',require_video=True)
    assert asset['frames']>=59 and len(asset['waveform'])>1
    assert audio_metadata(media.parent,aid)['id']==aid
    plan=EditPlanV2(source_volume=0,segments=[{'id':'s','source_in':0,'duration':60,'audio':[{'id':'a','asset_id':aid,'start':15,'end':45,'source_in':0,'volume':.5}]}]).model_dump()
    out=media.parent/'mixed.mp4';render_v2(media,plan,out,preview=True)
    def samples(t):return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(out),'-t','0.15','-ac','1','-ar','8000','-f','f32le','-']),dtype='<f4')
    assert np.max(np.abs(samples(.1)))<.001
    data=samples(.8);frequency=np.fft.rfftfreq(len(data),1/8000)[np.argmax(np.abs(np.fft.rfft(data)))];assert abs(frequency-730)<15
    assert np.max(np.abs(samples(1.8)))<.001

def test_audio_metadata_scoped_to_project(media,tmp_path,monkeypatch):
    from app import main
    aid=str(uuid4());normalize_audio(media,media.parent,aid,'Test','upload')
    plan=EditPlanV2(segments=[{'id':'s','source_in':0,'duration':60,'audio':[{'id':'a','asset_id':aid,'start':0,'end':30}]}])
    monkeypatch.setattr(main,'project_dir',lambda _:tmp_path/'other')
    with pytest.raises(HTTPException) as exc:validate_plan(plan,SimpleNamespace(id='other',duration=2))
    assert exc.value.status_code==422
    monkeypatch.setattr(main,'project_dir',lambda _:tmp_path)
    plan.segments[0].audio[0].source_in=asset_end=1000
    with pytest.raises(HTTPException):validate_plan(plan,SimpleNamespace(id='here',duration=2))

def test_old_plan_defaults_and_audio_bounds():
    p=EditPlanV2(segments=[{'id':'s','source_in':0,'duration':30}])
    assert p.source_volume==1 and p.segments[0].audio==[]
    with pytest.raises(ValidationError):EditPlanV2(segments=[{'id':'s','source_in':0,'duration':30,'audio':[{'id':'a','asset_id':str(uuid4()),'start':0,'end':31}]}])

def test_public_url_extraction_uses_validated_provider(media,monkeypatch):
    import yt_dlp
    from unittest.mock import MagicMock
    import shutil
    client=MagicMock();client.__enter__.return_value=client
    client.extract_info.return_value={'duration':2,'title':'TikTok fixture'}
    def factory(opts):
        assert 'vcodec!=none' in opts['format'] and 'format_id!^=download' in opts['format']
        assert opts['impersonate'].client=='chrome'
        def download(urls):shutil.copyfile(media,Path(opts['outtmpl'].replace('%(ext)s','mp4')))
        client.download.side_effect=download;return client
    monkeypatch.setattr(yt_dlp,'YoutubeDL',factory)
    result=import_audio(media.parent,{'mode':'url','platform':'tiktok','url':'https://www.tiktok.com/@creator/video/1234567890123456789','asset_id':str(uuid4())})
    assert result['origin']=='tiktok' and result['frames']>=59


def test_tiktok_video_format_never_selects_music_or_download():
    import yt_dlp
    formats=[{'format_id':'audio','url':'https://example.com/music.m4a','vcodec':'none','acodec':'aac','ext':'m4a'},
             {'format_id':'download','url':'https://example.com/outro.mp4','vcodec':'h264','acodec':'aac','ext':'mp4'},
             {'format_id':'play','url':'https://example.com/actual.mp4','vcodec':'h264','acodec':'aac','ext':'mp4'}]
    with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
        selector=ydl.build_format_selector('best[vcodec!=none][acodec!=none][format_id!^=download][format_note!*=?"watermarked"]')
        result=list(selector({'formats':formats,'has_merged_format':True,'incomplete_formats':False}))
        assert [f['format_id'] for f in result]==['play']
        assert not list(selector({'formats':formats[:2],'has_merged_format':True,'incomplete_formats':False}))



def test_trim_closing_before_audio_enters_timeline(media):
    aid=str(uuid4());asset=normalize_audio(media,media.parent,aid,'Cut closing','tiktok',require_video=True,trim_end_seconds=.5)
    assert 1.45<asset['duration']<1.58
    assert asset['trim_end_seconds']==.5
    assert asset['original_duration']>=2
    with pytest.raises(RuntimeError,match='terlalu panjang'):
        normalize_audio(media,media.parent,str(uuid4()),'Too short','tiktok',trim_end_seconds=3)
