import pytest
@pytest.fixture(autouse=True)
def private_key_file(tmp_path,monkeypatch):
    from app import key_store,gemini_connections,model_catalog
    monkeypatch.setattr(key_store,'PATH',tmp_path/'apikey.json')
    monkeypatch.setattr(key_store,'MARKER',tmp_path/'key-initialized')
    monkeypatch.setattr(gemini_connections,'STORAGE',tmp_path)
    monkeypatch.setattr(model_catalog,'STORAGE',tmp_path)
    for name in ('gemini_api_key','gemini_api_key_2','gemini_api_key_3'):monkeypatch.setattr(key_store.settings,name,'')

@pytest.fixture(autouse=True)
def metadata_jobs_are_isolated(monkeypatch,tmp_path):
    from app import model_catalog,gemini_connections
    monkeypatch.setattr(model_catalog,'on_refresh',lambda:None)
    def forbid_network(*args,**kwargs):
        raise AssertionError('Tests must supply a fake Gemini client')
    monkeypatch.setattr(gemini_connections,'client',forbid_network)
    yield
    for name,future in list(model_catalog._pending.items()):
        if str(tmp_path) in name:
            future.result(timeout=5)
            model_catalog._pending.pop(name,None)
