import json, urllib.request
base='http://localhost:8000/api'
def api(path,body=None,method=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req) as r:return json.load(r)
clips=api('/projects/a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07/clips')
titles=['Punya Sistem, Bukan Cuma Ikut Sinyal','Pernah Mau Menyerah? Ini Jawabannya','Jangan Kejar Cepat Kaya: Bertahan Dulu']
for i,c in enumerate(clips):
    c['plan']['layouts']=[{'start':0,'mode':'a','a':.5,'b':.7}]
    c['plan']['style']['margin']=300
    c['plan']['style']['size']=62
    saved=api('/clips/'+c['id'],{'title':titles[i],'plan':c['plan'],'revision':c['revision']},'PATCH')
    print(saved['id'],saved['revision'])
job=api('/clips/'+clips[0]['id']+'/preview',{})
print('preview',job['id'])
