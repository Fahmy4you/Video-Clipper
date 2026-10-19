import json,time,urllib.request,subprocess
from pathlib import Path
base='http://localhost:8000/api'
pid='a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07'
qa=Path('storage/qa/video-test')
def api(path,body=None,method=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
clips=api('/projects/'+pid+'/clips')
corrections=json.loads((qa/'audio-corrections.json').read_text())['corrections']
(qa/'clips-before-corrections.json').write_text(json.dumps(clips,ensure_ascii=False,indent=2))
report=[]
for c in clips:
    words=c['plan']['words']; seen=set()
    for change in corrections:
        if change['clip_id']!=c['id']:continue
        n=change['index']
        if not isinstance(n,int) or n<0 or n>=len(words) or n in seen:raise ValueError('Invalid correction index')
        seen.add(n)
        words[n]['text']=change['text'].strip()
    if c['id']=='f9f70789-54c7-4609-96c0-301ab0cf58c6':
        for w in words:
            if w['text']=='tanggal':w['text']='tangga'
    shift={'f9f70789-54c7-4609-96c0-301ab0cf58c6':.08,'555a0faf-91f1-4df6-8705-5c0d1adbdba0':7.4}.get(c['id'],0)
    c['plan']['start']=round(c['plan']['start']+shift,3)
    c['plan']['words']=[{**w,'start':max(0,round(w['start']-shift,3)),'end':round(w['end']-shift,3)} for w in words if w['text'] and w['end']>shift+.001]
    saved=api('/clips/'+c['id'],{'title':c['title'],'plan':c['plan'],'revision':c['revision']},'PATCH')
    job=api('/clips/'+c['id']+'/exports',{})
    print('Rendering',c['title'],job['id'],flush=True)
    while job['status'] in ('queued','running'):
        time.sleep(3);job=api('/jobs/'+job['id'])
    if job['status']!='succeeded':raise RuntimeError(job.get('error'))
    path=Path('storage/projects')/pid/(job['id']+'.mp4')
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
    v=next(s for s in data['streams'] if s['codec_type']=='video')
    assert (v['width'],v['height'])==(1080,1920)
    assert any(s['codec_type']=='audio' for s in data['streams'])
    duration=float(data['format']['duration'])
    assert abs(duration-(c['plan']['end']-c['plan']['start']))<.15
    report.append({'clip_id':c['id'],'title':c['title'],'job_id':job['id'],'path':str(path),'duration':duration,'width':v['width'],'height':v['height'],'revision':saved['revision'],'corrections':len(seen),'audio':True})
    (qa/'exports.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('Verified',c['title'],duration,flush=True)
