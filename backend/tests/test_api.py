from fastapi.testclient import TestClient
from app.main import app
from app import db

def test_unconfigured_database_is_actionable(monkeypatch):
    monkeypatch.setattr(db,'engine',None)
    response=TestClient(app).get('/api/projects')
    assert response.status_code==503
    assert 'DATABASE_URL' in response.json()['detail']
def test_foreign_webpage_cannot_start_job():
    response=TestClient(app).post('/api/projects/anything/analysis',headers={'Origin':'https://example.org'})
    assert response.status_code==403
def test_invalid_host():
    response=TestClient(app).get('/api/health',headers={'Host':'untrusted.example'})
    assert response.status_code==400
