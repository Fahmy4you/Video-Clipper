import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from app import key_store as store,gemini_connections as pool,gemini_config_api as routes,main,model_catalog


def add(name='Main',key='test-secret'):
    _,revision=store.read()
    return store.save(revision,lambda rows:rows.append({'id':name,'name':name,'key':key,'priority':len(rows)+1}))

def test_migration_once_and_empty_file_never_falls_back(monkeypatch):
    monkeypatch.setattr(store.settings,'gemini_api_key','legacy-secret')
    monkeypatch.setattr(store.settings,'gemini_api_key_2','legacy-secret')
    value,revision=store.read();assert len(value['connections'])==1
    monkeypatch.setattr(store.settings,'gemini_api_key','different-secret')
    assert store.read()[0]['connections'][0]['key']=='legacy-secret'
    store.save(revision,lambda rows:rows.clear())
    assert pool.connections()==[]
    store.PATH.unlink()
    assert pool.connections()==[]  # Deleting JSON must not resurrect legacy .env keys.
    assert store.PATH.stat().st_mode&0o777==0o600

def test_reload_and_fingerprint_changes_without_restart():
    add();before=pool.connections()[0]
    value,revision=store.read();store.save(revision,lambda rows:rows[0].update(key='replacement-secret'))
    after=pool.connections()[0]
    assert before.config_id==after.config_id and before.id!=after.id
    assert 'replacement-secret' not in repr(after)

def test_bad_json_and_duplicate_keys_are_not_replaced():
    store.PATH.write_text('{BROKEN')
    with pytest.raises(store.KeyConfigError):store.read()
    assert store.PATH.read_text()=='{BROKEN'
    store.PATH.unlink();add()
    _,revision=store.read()
    with pytest.raises(store.KeyConfigError):store.save(revision,lambda rows:rows.append({'id':'other','name':'Other','key':'test-secret','priority':2}))
    assert len(pool.connections())==1

def test_concurrent_saves_require_matching_revision():
    _,revision=store.read()
    def save(n):
        try:store.save(revision,lambda rows:rows.append({'id':str(n),'name':str(n),'key':'secret-'+str(n),'priority':1}));return True
        except store.KeyConflict:return False
    with ThreadPoolExecutor(2) as executor:results=list(executor.map(save,[1,2]))
    assert sorted(results)==[False,True]
    assert not store.PATH.with_name('apikey.json.tmp').exists()

def test_api_crud_reorder_test_and_no_secret_echo(monkeypatch):
    monkeypatch.setattr(routes,'changed',lambda:None);monkeypatch.setattr(routes,'verify_new',lambda _:None)
    client=TestClient(main.app);config=client.get('/api/gemini-config').json()
    response=client.post('/api/gemini-config',json={'revision':config['revision'],'name':'Main','key':'private-one'});assert response.status_code==201
    assert 'private-one' not in response.text and 'key' not in response.json()['connections'][0]
    first=response.json();ident=first['connections'][0]['id']
    second=client.post('/api/gemini-config',json={'revision':first['revision'],'name':'Backup','key':'private-two'}).json()
    ids=[c['id'] for c in second['connections']]
    ordered=client.patch('/api/gemini-config/order',json={'revision':second['revision'],'ids':ids[::-1]}).json();assert ordered['connections'][0]['label']=='Backup'
    assert client.patch('/api/gemini-config/'+ident,json={'revision':first['revision'],'name':'Old','key':'private-replaced'}).status_code==409
    edited=client.patch('/api/gemini-config/'+ident,json={'revision':ordered['revision'],'name':'New main','key':'private-replaced'}).json()
    assert 'private-replaced' not in json.dumps(edited)
    assert client.post('/api/gemini-config/'+ident+'/test',json={'model':'gemini-test'}).json()['ok']
    deleted=client.request('DELETE','/api/gemini-config/'+ident,json={'revision':edited['revision']}).json();assert len(deleted['connections'])==1
    rejected=client.post('/api/gemini-config',json={'name':5,'key':'private-leak-test'})
    assert rejected.status_code==422 and 'private-leak-test' not in rejected.text
    too_long=client.post('/api/gemini-config',json={'revision':deleted['revision'],'name':'x'*41,'key':'private-name-limit'})
    assert too_long.status_code==422 and 'private-name-limit' not in too_long.text

def test_invalid_json_does_not_kill_health(monkeypatch):
    store.PATH.write_text('{broken')
    response=TestClient(main.app).get('/api/health')
    assert response.status_code==200 and response.json()['gemini'] is False
    assert TestClient(main.app).get('/api/gemini-config').status_code==503


@pytest.mark.parametrize('count',[4,5])
def test_json_accepts_four_and_five_connections(count):
    rows=[{'id':str(n),'name':'Connection '+str(n),'key':'test-key-'+str(n),'priority':n} for n in range(1,count+1)]
    store.PATH.write_text(json.dumps({'version':1,'connections':rows}))
    assert len(pool.connections())==count
    assert [c.priority for c in pool.connections()]==list(range(1,count+1))


def test_sixth_connection_and_priority_six_are_rejected():
    for n in range(1,6):add('Connection '+str(n),'test-key-'+str(n))
    before=store.PATH.read_bytes();_,revision=store.read()
    with pytest.raises(store.KeyConfigError,match='maksimal 5'):
        store.save(revision,lambda rows:rows.append({'id':'six','name':'Six','key':'test-sixth','priority':6}))
    assert store.PATH.read_bytes()==before
    value,_=store.read();value['connections'][-1]['priority']=6
    with pytest.raises(store.KeyConfigError,match='1 sampai 5'):store.validate(value)


def test_api_fifth_connection_and_five_item_reorder(monkeypatch):
    monkeypatch.setattr(routes,'changed',lambda:None);monkeypatch.setattr(routes,'verify_new',lambda _:None)
    client=TestClient(main.app);config=client.get('/api/gemini-config').json()
    assert config['max_connections']==5
    for n in range(1,6):
        response=client.post('/api/gemini-config',json={'revision':config['revision'],'name':'Connection '+str(n),'key':'five-test-secret-'+str(n)})
        assert response.status_code==201 and 'five-test-secret' not in response.text
        config=response.json()
    assert len(config['connections'])==5
    before=store.PATH.read_bytes()
    sixth=client.post('/api/gemini-config',json={'revision':config['revision'],'name':'Six','key':'sixth-secret'})
    assert sixth.status_code==422 and 'sixth-secret' not in sixth.text and store.PATH.read_bytes()==before
    ids=[c['id'] for c in config['connections']][::-1]
    reordered=client.patch('/api/gemini-config/order',json={'revision':config['revision'],'ids':ids})
    assert reordered.status_code==200
    assert [c['id'] for c in reordered.json()['connections']]==ids
    assert [c['priority'] for c in reordered.json()['connections']]==[1,2,3,4,5]
