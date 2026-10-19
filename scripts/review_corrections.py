import json,urllib.request
from pathlib import Path
with urllib.request.urlopen('http://localhost:8000/api/projects/a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07/clips') as r: clips=json.load(r)
fixes=json.loads(Path('storage/qa/video-test/audio-corrections.json').read_text())['corrections']
for c in clips:
    words=c['plan']['words']
    for f in fixes:
        if f['clip_id']==c['id']:words[f['index']]['text']=f['text']
    print(c['title']);print(' '.join(w['text'] for w in words if w['text']))
