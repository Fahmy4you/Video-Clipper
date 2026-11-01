from types import SimpleNamespace
from unittest.mock import MagicMock
import json,time
import pytest
from app import gemini_connections as pool,model_catalog as catalog

class ProviderError(Exception):
    def __init__(self,code,detail):self.code=code;self.response_json=detail;super().__init__(str(detail))

@pytest.fixture
def connections(monkeypatch,tmp_path):
    monkeypatch.setattr(pool,'STORAGE',tmp_path);monkeypatch.setattr(catalog,'STORAGE',tmp_path)
    for attr,value in [('gemini_api_key','secret-one'),('gemini_api_key_2','secret-two'),('gemini_api_key_3','secret-three')]:monkeypatch.setattr(pool.settings,attr,value)
    for c in pool.connections():
        pool.record_model(c,'gemini-fixed',True)
        catalog.write_cache(c,{'models':[{'id':'gemini-fixed','name':'Fixed'}],'fetched_at':time.time()})
    return pool.connections()

def fake_client(fn):
    def build(c,*args):
        obj=MagicMock();obj.__enter__.return_value=obj;obj.models.generate_content.side_effect=lambda **kw:fn(c,kw);return obj
    return build

def test_fallback_keeps_model_and_honors_cooldown(connections,monkeypatch):
    calls=[]
    def generate(c,kw):
        calls.append((c.label,kw['model']))
        if c.priority==1:raise ProviderError(429,{'retryDelay':'120s'})
        return SimpleNamespace(text='ok')
    monkeypatch.setattr(pool,'client',fake_client(generate))
    assert pool.generate('gemini-fixed','data',{}).text=='ok'
    assert calls==[('Utama','gemini-fixed'),('Cadangan 1','gemini-fixed')]
    calls.clear();pool.generate('gemini-fixed','data',{});assert calls==[('Cadangan 1','gemini-fixed')]
    assert pool.cooldown(pool.state(connections[0]),'gemini-fixed')['until']>=time.time()+115

def test_all_daily_waits_without_guessing_reset(connections,monkeypatch):
    monkeypatch.setattr(pool,'client',fake_client(lambda *_:(_ for _ in ()).throw(ProviderError(429,{'quotaMetric':'requests_per_day'}))))
    with pytest.raises(pool.GeminiWait) as e:pool.generate('gemini-fixed','data',{})
    assert e.value.kind=='waiting_quota' and e.value.next_at is None
    for c in connections:assert pool.state(c)['cooldowns']['gemini-fixed']['manual']
    pool.clear_expired_for_manual('gemini-fixed');assert all(not pool.cooldown(pool.state(c),'gemini-fixed') for c in connections)

def test_invalid_key_disabled_but_unsupported_model_is_scoped(connections,monkeypatch):
    def generate(c,_):
        if c.priority==1:raise ProviderError(400,{'reason':'API_KEY_INVALID'})
        if c.priority==2:raise ProviderError(403,{'message':'model denied'})
        return SimpleNamespace(text='ok')
    monkeypatch.setattr(pool,'client',fake_client(generate));pool.generate('gemini-fixed','data',{})
    assert pool.state(connections[0])['disabled']
    assert not pool.state(connections[1]).get('disabled')
    assert pool.state(connections[1])['runtime_models']['gemini-fixed']['ok'] is False

def test_request_error_does_not_rotate_keys(connections,monkeypatch):
    calls=[]
    def generate(c,_):calls.append(c.id);raise ProviderError(400,{'message':'bad payload secret-one'})
    monkeypatch.setattr(pool,'client',fake_client(generate))
    with pytest.raises(RuntimeError) as e:pool.generate('gemini-fixed','data',{})
    assert len(calls)==1 and 'secret-one' not in str(e.value)

def test_max_three_transient_attempts_then_fallback(connections,monkeypatch):
    calls=[]
    def generate(c,_):
        calls.append(c.priority)
        if c.priority==1:raise ProviderError(503,{'retryDelay':'0s'})
        return SimpleNamespace(text='ok')
    monkeypatch.setattr(pool,'client',fake_client(generate));pool.generate('gemini-fixed','data',{})
    assert calls==[1,1,1,2]

def test_dedup_secret_redaction_and_public_status(connections,monkeypatch):
    from app import key_store
    key_store.PATH.unlink();key_store.MARKER.unlink()
    monkeypatch.setattr(pool.settings,'gemini_api_key_3','secret-two')
    assert len(pool.connections())==2
    pool.failure(connections[0],'gemini-fixed','quota',120)
    public=json.dumps(pool.public_connections());assert 'secret-' not in public
    assert pool.redact('secret-one / secret-two')=='[redacted] / [redacted]'

def test_model_union_and_cooldown_does_not_hide_known_access(connections,monkeypatch):
    for c in connections:catalog.write_cache(c,{'models':[{'id':'gemini-'+str(c.priority),'name':'Model'}],'fetched_at':time.time()})
    pool.failure(connections[0],'gemini-1','quota',120)
    assert {m['id'] for m in catalog.known_models()}=={'gemini-1','gemini-2','gemini-3'}
    catalog.validate_model('gemini-2')


def test_disabled_connection_cannot_be_revived_by_metadata(connections,monkeypatch):
    c=connections[0]
    catalog.write_cache(c,{'models':[{'id':'gemini-fixed','name':'Fixed'}],'fetched_at':time.time()})
    pool.failure(c,'gemini-fixed','invalid',None)
    assert not catalog.can_use(c,'gemini-fixed')
    assert pool.state(c)['disabled']


def test_automatic_backoff_is_capped_at_fifteen_minutes(connections,monkeypatch):
    monkeypatch.setattr(pool.time,'time',lambda:1000)
    monkeypatch.setattr(pool.random,'uniform',lambda *_:5)
    for _ in range(8):pool.failure(connections[0],'gemini-fixed','service',None)
    assert pool.state(connections[0])['cooldowns']['gemini-fixed']['until']==1900
    pool.failure(connections[0],'gemini-fixed','quota',3600)
    assert pool.state(connections[0])['cooldowns']['gemini-fixed']['until']==4600


def test_removed_key_is_not_reused_for_retry(connections,monkeypatch):
    from app import key_store
    calls=[]
    def generate(c,_):
        calls.append(c.priority)
        if c.priority==1:
            _,revision=key_store.read()
            key_store.save(revision,lambda rows:rows.pop(0))
            raise ProviderError(503,{'retryDelay':'0s'})
        return SimpleNamespace(text='ok')
    monkeypatch.setattr(pool,'client',fake_client(generate))
    assert pool.generate('gemini-fixed','data',{}).text=='ok'
    assert calls==[1,2]


def test_fallback_reaches_fifth_connection_with_same_model(connections,monkeypatch):
    from app import key_store
    _,revision=key_store.read()
    key_store.save(revision,lambda rows:rows.extend([{'id':str(n),'name':'Backup '+str(n),'key':'test-extra-'+str(n),'priority':n} for n in (4,5)]))
    for c in pool.connections():
        pool.record_model(c,'gemini-fixed',True)
        catalog.write_cache(c,{'models':[{'id':'gemini-fixed','name':'Fixed'}],'fetched_at':time.time()})
    calls=[]
    def generate(c,kw):
        calls.append((c.priority,kw['model']))
        if c.priority<5:raise ProviderError(429,{'retryDelay':'120s'})
        return SimpleNamespace(text='fifth works')
    monkeypatch.setattr(pool,'client',fake_client(generate))
    assert pool.generate('gemini-fixed','data',{}).text=='fifth works'
    assert calls==[(n,'gemini-fixed') for n in range(1,6)]
