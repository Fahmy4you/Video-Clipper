import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError
from app import tasks
from app.schemas import ModelSelection

@pytest.mark.parametrize('count,prompt',[(1,''),(5,''),(1,'Sekitar 1:32, money management'),(5,'Topik tidak ada, timestamp 99:00')])
def test_analysis_limits_priorities_and_report(monkeypatch,tmp_path,count,prompt):
    (tmp_path/'source.mp4').touch()
    words=[{'start':i,'end':i+.7,'text':('Money management.' if i==92 else 'Konteks.')} for i in range(300)]
    (tmp_path/'transcript.json').write_text(json.dumps({'words':words}))
    project=SimpleNamespace()
    session=MagicMock(); session.__enter__.return_value=session;session.get.side_effect=lambda model,_: job if model is tasks.Job else project
    job=SimpleNamespace(payload={})
    session.scalars.return_value.all.return_value=[]
    monkeypatch.setattr(tasks,'Session',MagicMock(return_value=session))
    monkeypatch.setattr(tasks,'probe',lambda _: {'streams':[{'codec_type':'audio'}],'format':{'duration':'300'}})
    monkeypatch.setattr(tasks,'update',MagicMock());monkeypatch.setattr(tasks,'check',MagicMock())
    monkeypatch.setattr(tasks.settings,'gemini_api_key','test-only')
    from google import genai
    client=MagicMock();monkeypatch.setattr(genai,'Client',MagicMock(return_value=client))
    missing='99:00' in prompt
    clips=[{'start':a,'end':a+35,'title':str(a),'reason':'Konteks utuh','fulfills_prompt':a==80 and not missing and bool(prompt)} for a in (0,40,80,120,160)]
    client.models.generate_content.return_value.text=json.dumps({'clips':clips,'unmet_requests':['Topik tidak ditemukan; 99:00 di luar durasi.'] if missing else []})
    tasks.analyze('j','p','unused',tmp_path,'gemini-test',count,prompt)
    saved=[call.args[0] for call in session.add.call_args_list]
    assert len(saved)==count
    assert all(c.plan['segments'][0]['transform']['mode']=='fill' for c in saved)
    assert project.analysis_report['generated']==count
    assert len(job.payload['mix_target_ids'])==count
    request=client.models.generate_content.call_args.kwargs
    assert request['model']=='gemini-test' and f'maksimal {count}' in request['contents']
    assert prompt in request['contents']
    if '1:32' in prompt:
        assert saved[0].fulfills_prompt
        segment=saved[0].plan['segments'][0]
        assert segment['source_in']<92*30<segment['source_in']+segment['duration']
    if missing:assert project.analysis_report['unmet_requests']
    # Re-analysis must not replace a user's edited clips.
    session.add.reset_mock();session.scalars.return_value.all.return_value=[object()]
    tasks.analyze('j','p','unused',tmp_path,'gemini-test',count,prompt)
    session.add.assert_not_called()
    client.models.generate_content.return_value.text=json.dumps({'clips':[],'unmet_requests':['Materi tidak cukup.']})
    with pytest.raises(RuntimeError,match='Tidak ditemukan highlight valid'):
        tasks.analyze('j','p','unused',tmp_path,'gemini-test',count,prompt)
    assert project.analysis_report['generated']==0
    assert project.analysis_report['unmet_requests']==['Materi tidak cukup.']

def test_project_update_cannot_change_locked_ratio():
    with pytest.raises(ValidationError):
        ModelSelection(gemini_model='gemini-test',aspect_ratio='16:9')
