import json, urllib.request
base='http://localhost:8000/api'
pid='a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07'
with urllib.request.urlopen(base+'/projects/'+pid+'/clips') as r: clips=json.load(r)
for c in clips:
    print(c['id'], c['title'], c['plan']['start'],c['plan']['end'])
    print(c['reason'])
    print(' '.join(w['text'] for w in c['plan']['words']))
