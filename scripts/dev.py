import os,sys,subprocess,signal,socket,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
PY=ROOT/'.venv/bin/python'
if not PY.exists(): sys.exit('Jalankan bash scripts/setup.sh terlebih dahulu.')
for port in (5173,8000,6381):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',port))==0: sys.exit(f'Port {port} sedang dipakai. Hentikan launcher proyek sebelumnya dahulu.')
env={**os.environ,'PYTHONPATH':str(ROOT/'backend')}
subprocess.run([str(PY),'scripts/doctor.py'],env=env,check=False)
configured=subprocess.run([str(PY),'-c','from app.config import settings; raise SystemExit(0 if settings.database_url else 1)'],env=env).returncode==0
if configured:
    result=subprocess.run([str(PY),'-m','alembic','-c','backend/alembic.ini','upgrade','head'],env=env)
    if result.returncode: print('Migrasi belum berhasil. UI tetap dibuka untuk petunjuk setup.',flush=True)
    else:
        subprocess.run([str(PY),'-c',"from app.db import Session,Job; from sqlalchemy import update; s=Session(); s.execute(update(Job).where(Job.status.in_(['running','queued'])).values(status='failed',stage='Terhenti',error='Launcher sebelumnya terhenti. Gunakan Coba lagi untuk melanjutkan.')); s.commit()"],env=env,check=True)
logs=ROOT/'storage/logs'; logs.mkdir(parents=True,exist_ok=True)
redis=ROOT/'storage/redis'; redis.mkdir(exist_ok=True)
children=[];handles=[]
def start(name,args):
    f=(logs/(name+'.log')).open('a');handles.append(f)
    p=subprocess.Popen(args,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    children.append((name,p));return p
def ready(port):
    for _ in range(60):
        for name,p in children:
            if p.poll() is not None: raise RuntimeError(f'{name} berhenti; baca storage/logs/{name}.log')
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',port))==0:return
        time.sleep(.5)
    raise RuntimeError(f'Port {port} belum siap; periksa log.')
def stop(*args): raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    start('redis',['redis-server','--bind','127.0.0.1','--port','6381','--dir',str(redis),'--appendonly','yes'])
    ready(6381)
    start('api',[str(PY),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'])
    ready(8000)
    start('worker',[str(PY),'-m','celery','-A','app.tasks:celery','worker','--loglevel=info','--concurrency=1','--pool=solo'])
    start('web',['npm','--prefix','apps/web','run','dev'])
    ready(5173)
    print('Video Clipping siap: http://localhost:5173 | API: http://localhost:8000/docs',flush=True)
    print('Ctrl+C untuk menghentikan semua layanan proyek. Log: storage/logs/',flush=True)
    while True:
        for name,p in children:
            if p.poll() is not None: raise RuntimeError(f'{name} berhenti. Baca log lalu jalankan ulang.')
        time.sleep(1)
except KeyboardInterrupt: print('Menghentikan layanan proyek...',flush=True)
finally:
    for name,p in reversed(children):
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    for f in handles:f.close()
