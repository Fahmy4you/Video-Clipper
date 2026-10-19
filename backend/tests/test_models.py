
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from app import model_catalog as catalog
from app.schemas import ProjectInput
from pydantic import ValidationError

def model(name,actions=None):
    return SimpleNamespace(name='models/'+name,display_name=name,supported_actions=actions or ['generateContent'])

def test_catalog_keeps_only_gemini_text_generators():
    result=catalog.text_models([model('gemini-fast'),model('gemini-pro'),model('gemini-image'),model('gemini-tts'),model('gemini-live'),model('gemini-nano-banana-2.1'),model('gemini-transcribe'),model('embedding',['embedContent']),model('gemini-fast')])
    assert [x['id'] for x in result]==['gemini-fast','gemini-pro']

def test_model_required_in_new_project():
    with pytest.raises(ValidationError):ProjectInput(url='https://youtu.be/dQw4w9WgXcQ')

def test_provider_error_does_not_leak_key(monkeypatch):
    monkeypatch.setattr(catalog.settings,'gemini_api_key','PRIVATE-TEST-KEY')
    monkeypatch.setattr(catalog,'_cache',None)
    monkeypatch.setattr(catalog.genai,'Client',MagicMock(side_effect=RuntimeError('PRIVATE-TEST-KEY')))
    with pytest.raises(HTTPException) as exc:catalog.available_models()
    assert exc.value.status_code==503
    assert 'PRIVATE-TEST-KEY' not in exc.value.detail

def test_cache_refresh_and_selection_validation(monkeypatch,tmp_path):
    monkeypatch.setattr(catalog,'STORAGE',tmp_path)
    monkeypatch.setattr(catalog.settings,'gemini_api_key','test')
    monkeypatch.setattr(catalog,'_cache',None)
    client=MagicMock();client.__enter__.return_value=client
    client.models.list.return_value=[model('gemini-test')]
    client.models.generate_content.return_value.text='{"clips":[],"unmet_requests":[]}'
    monkeypatch.setattr(catalog.genai,'Client',MagicMock(return_value=client))
    assert catalog.available_models()[0]['id']=='gemini-test'
    assert catalog.validate_model('gemini-test')=='gemini-test'
    assert client.models.list.call_count==1
    catalog.available_models(refresh=True)
    assert client.models.list.call_count==2
    with pytest.raises(HTTPException) as exc:catalog.validate_model('gemini-unknown')
    assert exc.value.status_code==422

def test_no_key_is_actionable(monkeypatch):
    monkeypatch.setattr(catalog.settings,'gemini_api_key','')
    with pytest.raises(HTTPException) as exc:catalog.available_models()
    assert 'GEMINI_API_KEY' in exc.value.detail


def test_analysis_uses_job_model_snapshot(monkeypatch,tmp_path):
    from app import tasks
    fake=MagicMock();fake.__enter__.return_value=fake
    fake.get.side_effect=[SimpleNamespace(status='queued',kind='analysis',project_id='p',payload={'gemini_model':'gemini-chosen'}),SimpleNamespace(id='p',url='https://example.invalid',gemini_model='gemini-changed-later')]
    monkeypatch.setattr(tasks,'Session',MagicMock(return_value=fake))
    monkeypatch.setattr(tasks,'project_dir',lambda _:tmp_path)
    monkeypatch.setattr(tasks,'update',MagicMock())
    monkeypatch.setattr(tasks.shutil,'disk_usage',lambda _:SimpleNamespace(free=10*1024**3))
    analyze=MagicMock(return_value={'message':'ok'});monkeypatch.setattr(tasks,'analyze',analyze)
    tasks.execute.run('job')
    assert analyze.call_args.args[4:] == ('gemini-chosen',3,'')

def test_probe_hides_inaccessible_and_non_json_models(monkeypatch,tmp_path):
    monkeypatch.setattr(catalog,'STORAGE',tmp_path)
    monkeypatch.setattr(catalog.settings,'gemini_api_key','test-access-key')
    monkeypatch.setattr(catalog,'_cache',None)
    client=MagicMock();client.__enter__.return_value=client
    client.models.list.return_value=[model('gemini-good'),model('gemini-argon'),model('gemini-invalid')]
    def generate(**kw):
        if kw['model']=='gemini-argon':raise RuntimeError('permission denied secret-key')
        return SimpleNamespace(text='not json' if kw['model']=='gemini-invalid' else '{"clips":[],"unmet_requests":[]}')
    client.models.generate_content.side_effect=generate
    monkeypatch.setattr(catalog.genai,'Client',MagicMock(return_value=client))
    assert [m['id'] for m in catalog.available_models()]==['gemini-good']
    assert client.models.generate_content.call_count==3
    monkeypatch.setattr(catalog,'_cache',None)
    assert len(catalog.available_models())==1
    assert client.models.generate_content.call_count==3
    catalog.record_unavailable('gemini-good')
    assert catalog.available_models()==[]
    assert 'test-access-key' not in catalog.cache_path().read_text()

def test_access_cache_is_scoped_to_key(monkeypatch,tmp_path):
    monkeypatch.setattr(catalog,'STORAGE',tmp_path)
    monkeypatch.setattr(catalog.settings,'gemini_api_key','first-key')
    catalog.record_access('gemini-test',True)
    monkeypatch.setattr(catalog.settings,'gemini_api_key','second-key')
    assert catalog.access_records()=={}
