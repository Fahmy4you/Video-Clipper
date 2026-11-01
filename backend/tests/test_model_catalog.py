from types import SimpleNamespace
from threading import Event, Lock
from unittest.mock import MagicMock
import json, time
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import model_catalog as catalog, gemini_connections as pool, key_store, main


def setup(count=1):
    _,rev=key_store.read()
    key_store.save(rev,lambda rows:rows.extend({'id':str(n),'name':str(n),'key':'catalog-test-secret-'+str(n),'priority':n} for n in range(1,count+1)))
    return pool.connections()


def model(name='gemini-test',actions=None):
    return SimpleNamespace(name='models/'+name,display_name=name,supported_actions=actions or ['generateContent'])


def fake(monkeypatch,handler):
    api=MagicMock();api.__enter__.return_value=api
    api.models.list.side_effect=handler
    api.models.generate_content.side_effect=AssertionError('Discovery must NEVER generate content')
    monkeypatch.setattr(pool,'client',lambda *_:api)
    return api


def page(models,token=None):
    return SimpleNamespace(page=models,config={'page_token':token})


def drain():
    for future in list(catalog._pending.values()):future.result(timeout=5)


def seed(c,models=None,age=0):
    catalog.write_cache(c,{'models':models or [{'id':'gemini-test','name':'Test'}],'fetched_at':time.time()-age})


def test_catalog_only_text_and_no_generation(monkeypatch):
    setup();api=fake(monkeypatch,lambda **_:page([model(),model(),model('gemini-image'),model('gemini-omni'),model('gemini-tts'),model('gemini-live'),model('embedding',['embedContent'])]))
    catalog.schedule();drain()
    result=catalog.snapshot(False)
    assert [m['id'] for m in result['models']]==['gemini-test']
    assert result['models'][0]['status']=='catalog' and result['models'][0]['selectable']
    api.models.generate_content.assert_not_called()
    assert api.models.list.call_args.kwargs['config']['page_size']==1000
    assert not pool.state(pool.connections()[0]).get('last_success')


def test_pagination_not_per_model_and_partial_failure_keeps_complete_cache(monkeypatch):
    c=setup()[0];tokens=[]
    def handler(config):
        tokens.append(config.get('page_token'))
        return page([model('gemini-a')],'next') if not config.get('page_token') else page([model('gemini-b')])
    api=fake(monkeypatch,handler);catalog.schedule();drain()
    assert tokens==[None,'next'] and len(catalog.known_models())==2
    old=catalog.read_cache(c)['fetched_at']
    def broken(config):
        if config.get('page_token'):raise TimeoutError()
        return page([model('gemini-partial')],'next')
    api.models.list.side_effect=broken;catalog.schedule(force=True);drain()
    data=catalog.read_cache(c)
    assert data['fetched_at']==old and {m['id'] for m in data['models']}=={'gemini-a','gemini-b'}
    assert data['next_attempt_at']>=time.time()+55
    api.models.generate_content.assert_not_called()


def test_five_connections_two_at_a_time_nonblocking_incremental_snapshot(monkeypatch):
    setup(5);release=Event();entered=Event();guard=Lock();counts={'active':0,'peak':0,'calls':0}
    def handler(**_):
        with guard:
            counts['active']+=1;counts['calls']+=1;counts['peak']=max(counts['peak'],counts['active'])
            if counts['active']==2:entered.set()
        release.wait(3)
        with guard:counts['active']-=1
        return page([model()])
    api=fake(monkeypatch,handler)
    started=time.monotonic();view=catalog.snapshot();assert time.monotonic()-started<.5 and view['refreshing']
    assert entered.wait(2)
    for _ in range(5):catalog.schedule(force=True)
    release.set();drain()
    assert counts['calls']==5 and counts['peak']==2
    assert len(catalog.known_models())==1 and len(catalog.known_models()[0]['connections'])==5
    api.models.generate_content.assert_not_called()


def test_fast_connection_visible_while_other_pending(monkeypatch):
    conns=setup(2);release=Event();entered=Event()
    def client(c,*_):
        api=MagicMock();api.__enter__.return_value=api
        def listing(**_):
            if c.priority==2:entered.set();release.wait(3)
            return page([model('gemini-'+str(c.priority))])
        api.models.list.side_effect=listing;return api
    monkeypatch.setattr(pool,'client',client);catalog.schedule();assert entered.wait(2)
    for f in list(catalog._pending.values()):
        if f.done():f.result()
    limit=time.monotonic()+2
    while not catalog.read_cache(conns[0]) and time.monotonic()<limit:time.sleep(.01)
    view=catalog.snapshot(False)
    assert [m['id'] for m in view['models']]==['gemini-1'] and view['refreshing']
    release.set();drain()


def test_persistent_stale_cache_validation_without_network(monkeypatch):
    c=setup()[0];seed(c,age=90000)
    assert catalog.validate_model('gemini-test')=='gemini-test'
    api=fake(monkeypatch,lambda **_:page([model()]))
    catalog._pending.clear()  # Simulate an API-process restart; disk cache remains.
    assert catalog.snapshot(False)['models'][0]['stale']
    catalog.snapshot();drain();assert not catalog.snapshot(False)['stale']
    before=api.models.list.call_count;catalog.snapshot();drain();assert api.models.list.call_count==before


def test_changed_key_discards_inflight_results_name_and_priority_preserve_cache(monkeypatch):
    c=setup()[0];seed(c);release=Event();entered=Event()
    def listing(**_):entered.set();release.wait(3);return page([model('gemini-old')])
    api=fake(monkeypatch,listing);catalog.schedule(force=True);assert entered.wait(2)
    _,rev=key_store.read();key_store.save(rev,lambda rows:rows[0].update(name='Renamed'))
    assert catalog.listed(pool.connections()[0],'gemini-test')
    _,rev=key_store.read();key_store.save(rev,lambda rows:rows[0].update(key='replacement-secret'))
    release.set();drain()
    assert catalog.known_models()==[] and catalog.read_cache(c)['models'][0]['id']=='gemini-test'
    api.models.generate_content.assert_not_called()


def test_metadata_does_not_clear_inference_denial_or_cooldown(monkeypatch):
    c=setup()[0];seed(c);pool.failure(c,'gemini-test','unsupported',None)
    pool.failure(c,'gemini-test','quota',120)
    before=pool.cooldown(pool.state(c),'gemini-test')
    fake(monkeypatch,lambda **_:page([model()]));catalog.schedule(force=True);drain()
    item=catalog.known_models()[0];assert item['status']=='denied' and not item['selectable']
    assert pool.cooldown(pool.state(c),'gemini-test')==before
    pool.clear_expired_for_manual('gemini-test')
    assert pool.cooldown(pool.state(c),'gemini-test')==before
    assert catalog.known_models()[0]['status']=='waiting_quota'


def test_legacy_probe_cache_is_not_real_history():
    c=setup()[0];seed(c)
    pool.state(c,lambda s:s.update(models={'gemini-test':{'ok':True}},last_success=time.time()))
    assert catalog.known_models()[0]['status']=='catalog'
    assert pool.public_connections()[0]['used_models']==[]


def test_only_validated_real_request_records_success(monkeypatch):
    c=setup()[0];seed(c);api=MagicMock();api.__enter__.return_value=api
    api.models.generate_content.return_value=SimpleNamespace(text='{"items":[]}')
    monkeypatch.setattr(pool,'client',lambda *_:api)
    pool.generate('gemini-test','REAL USER JOB',{},validate=json.loads)
    assert catalog.known_models()[0]['status']=='used'
    api.models.list.assert_not_called()
    assert api.models.generate_content.call_args.kwargs['contents']=='REAL USER JOB'
    api.models.generate_content.return_value.text='bad json'
    with pytest.raises(RuntimeError):pool.generate('gemini-test','REAL USER JOB',{},validate=json.loads)
    assert api.models.generate_content.call_count==2


def test_new_unverified_model_goes_directly_to_real_work_and_fallback(monkeypatch):
    conns=setup(2)
    for c in conns:seed(c)
    calls=[]
    class Denied(Exception):code=403
    def client(c,*_):
        api=MagicMock();api.__enter__.return_value=api
        def generate(**kwargs):
            calls.append((c.priority,kwargs))
            if c.priority==1:raise Denied()
            return SimpleNamespace(text='{}')
        api.models.generate_content.side_effect=generate
        api.models.list.side_effect=AssertionError('No preliminary metadata fetch')
        return api
    monkeypatch.setattr(pool,'client',client)
    pool.generate('gemini-test','REAL ANALYSIS',{},validate=json.loads)
    assert [(n,k['model'],k['contents']) for n,k in calls]==[(1,'gemini-test','REAL ANALYSIS'),(2,'gemini-test','REAL ANALYSIS')]
    assert catalog.known_models()[0]['selectable']


def test_http_metadata_routes_and_submit_validation_never_probe(monkeypatch):
    from app import gemini_config_api
    monkeypatch.setattr(gemini_config_api,'changed',lambda:None)
    c=setup()[0];api=fake(monkeypatch,lambda **_:page([model()]))
    http=TestClient(main.app)
    assert http.post('/api/model-catalog/refresh',json={}).status_code==202;drain()
    assert http.get('/api/model-catalog').json()['models'][0]['status']=='catalog'
    assert catalog.validate_model('gemini-test')=='gemini-test'
    assert http.get('/api/models?refresh=true').status_code==200;drain()
    assert http.post('/api/gemini-config/'+c.config_id+'/test',json={'model':'gemini-test'}).status_code==202;drain()
    revision=http.get('/api/gemini-config').json()['revision']
    response=http.post('/api/gemini-config',json={'revision':revision,'name':'Backup','key':'test-new-secret'})
    assert response.status_code==201;drain()
    assert 'test-new-secret' not in response.text
    revision=response.json()['revision'];ident=response.json()['connections'][-1]['id']
    assert http.patch('/api/gemini-config/'+ident,json={'revision':revision,'name':'Changed','key':'test-other-secret'}).status_code==200;drain()
    api.models.generate_content.assert_not_called()


def test_metadata_error_is_sanitized_and_backoff_bounded(monkeypatch):
    c=setup()[0]
    fake(monkeypatch,lambda **_:(_ for _ in ()).throw(RuntimeError(c.key)))
    for attempt,delay in enumerate([60,300,900,900],1):
        data=catalog.read_cache(c);data['next_attempt_at']=None;catalog.write_cache(c,data)
        catalog.schedule(force=True);drain();data=catalog.read_cache(c)
        assert delay-2<data['next_attempt_at']-time.time()<=delay
        assert c.key not in json.dumps(data)
    assert data['attempts']==4


def test_per_request_deadline_and_incomplete_page_are_bounded(monkeypatch):
    c=setup()[0];seed(c);clock=[0]
    monkeypatch.setattr(catalog,'monotonic',lambda:clock[0])
    configs=[]
    def listing(config):
        configs.append(config);clock[0]+=16
        return page([model('gemini-unfinished')],'more')
    fake(monkeypatch,listing);catalog.schedule(force=True);drain()
    assert [x['http_options']['timeout'] for x in configs]==[15000,14000]
    assert catalog.listed(c,'gemini-test') and not catalog.listed(c,'gemini-unfinished')


def test_empty_catalog_configuration_and_invalid_selection():
    assert catalog.snapshot(False)['connections']==[]
    with pytest.raises(HTTPException) as e:catalog.validate_model('gemini-unknown')
    assert e.value.status_code==409
    c=setup()[0];seed(c)
    with pytest.raises(HTTPException) as e:catalog.validate_model('gemini-unknown')
    assert e.value.status_code==422


def test_completed_refresh_is_read_before_reporting_idle(monkeypatch):
    c=setup()[0]
    def finished(_):
        seed(c)
        return False
    monkeypatch.setattr(catalog,'refreshing',finished)
    view=catalog.snapshot(False)
    assert not view['refreshing'] and view['models'][0]['id']=='gemini-test'
