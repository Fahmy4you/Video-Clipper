import json,urllib.request,time
from pathlib import Path
base='http://localhost:8000/api'
def api(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
clips=api('/projects/a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07/clips')
results=[]
for c in clips:
    job=api('/clips/'+c['id']+'/preview',{})
    while job['status'] in ('queued','running'):
        time.sleep(3);job=api('/jobs/'+job['id'])
    print(job['id'],job['status'],flush=True)
    results.append(job)
Path('storage/qa/video-test/previews.json').write_text(json.dumps(results,indent=2))
