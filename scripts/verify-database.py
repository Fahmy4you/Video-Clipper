
"""Exercise actual API persistence, then remove only the temporary project created by this check."""
import httpx
from app.db import Session,Project
created_id=None
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
    health=client.get('/api/health');health.raise_for_status()
    assert health.json()['database']=='ready',health.json()
    print('API health: database ready')
    models=client.get('/api/models');models.raise_for_status();choices=models.json()
    assert choices,'No model available'
    try:
        result=client.post('/api/projects',json={'url':'https://youtu.be/dQw4w9WgXcQ','gemini_model':choices[0]['id']})
        result.raise_for_status();created=result.json();created_id=created['id']
        with Session() as s:
            assert s.get(Project,created_id).gemini_model==choices[0]['id']
        changed=choices[-1]['id']
        result=client.patch('/api/projects/'+created_id+'/model',json={'gemini_model':changed})
        result.raise_for_status()
        read=client.get('/api/projects/'+created_id);read.raise_for_status()
        assert read.json()['gemini_model']==changed
        with Session() as s:
            assert s.get(Project,created_id).gemini_model==changed
        print('Create/read/update project model: PASS (real PostgreSQL)')
    finally:
        if created_id:
            with Session() as s:
                fixture=s.get(Project,created_id)
                if fixture:s.delete(fixture);s.commit()
            print('Temporary verification project removed')
