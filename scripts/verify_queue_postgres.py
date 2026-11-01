"""Real PostgreSQL + OS-process queue validation, isolated from user data."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.db import Base,Project,Job,VideoClip

def configure(schema,root,lockroot):
    from app import queue_runtime as queue,tasks,media,video_library as library
    engine=create_engine(settings.database_url,connect_args={'options':'-c search_path='+schema})
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    for m in (queue,tasks,library):m.Session=factory
    queue.engine=engine;queue.STORAGE=Path(lockroot)
    tasks.STORAGE=media.STORAGE=library.STORAGE=Path(root)
    return engine,factory,queue,tasks

def worker(schema,root,lockroot,mode):
    engine,factory,queue,tasks=configure(schema,root,lockroot)
    if mode!='media':
        def process(jid):
            with factory() as s:
                j=s.get(Job,jid)
                running=list(s.scalars(select(Job.id).where(Job.status=='running')))
                if running!=[jid]:raise AssertionError('Concurrent running jobs')
                j.checkpoint={**j.checkpoint,'starts':j.checkpoint.get('starts',0)+1};s.commit()
            with (Path(root)/'trace.jsonl').open('a') as f:f.write(json.dumps({'event':'start','id':jid,'time':time.time()})+'\n')
            if mode=='crash':
                (Path(root)/'started').write_text(jid)
                time.sleep(30)
            time.sleep(.4)
            with factory() as s:
                j=s.get(Job,jid);j.status='succeeded';s.commit()
            with (Path(root)/'trace.jsonl').open('a') as f:f.write(json.dumps({'event':'end','id':jid,'time':time.time()})+'\n')
        tasks.process_job=process
    for _ in range(18):
        tasks.execute.run()
        with factory() as s:
            if not s.scalar(select(Job.id).where(Job.status.in_(queue.PENDING))):break
        time.sleep(.2)
    engine.dispose()

if len(sys.argv)>1:
    worker(*sys.argv[1:]);raise SystemExit()

schema='qa_queue_'+uuid4().hex
admin=create_engine(settings.database_url)
with admin.begin() as conn:conn.execute(text('CREATE SCHEMA '+schema))
try:
    with tempfile.TemporaryDirectory(prefix='video-queue-qa-') as tmp:
        root=Path(tmp);engine,factory,queue,tasks=configure(schema,root,root/'lock')
        Base.metadata.create_all(engine)
        with factory() as s:
            p=Project(url='fixture');s.add(p);s.flush();pid=p.id
            ids=[]
            for kind in ['analysis','export','audio_import','editor_media']:
                j=Job(project_id=pid,kind=kind);s.add(j);s.flush();ids.append(j.id)
            s.commit()
        def launch(lock,mode='normal'):
            return subprocess.Popen([sys.executable,__file__,schema,str(root),str(root/lock),mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        # Different lock directories deliberately bypass flock: PostgreSQL must serialize.
        workers=[launch('worker-a'),launch('worker-b')]
        for proc in workers:
            out,err=proc.communicate(timeout=45)
            assert proc.returncode==0,err.decode()[-1200:]
        events=[json.loads(line) for line in (root/'trace.jsonl').read_text().splitlines()]
        assert [e['event'] for e in events]==['start','end']*4,events
        assert [e['id'] for e in events if e['event']=='start']==ids
        with factory() as s:assert all(j.checkpoint['starts']==1 for j in s.scalars(select(Job)))
        # Kill an actual owner; a fresh process recovers its checkpoint and completes once.
        with factory() as s:j=Job(project_id=pid,kind='analysis',checkpoint={'saved':'transcript'});s.add(j);s.commit();crash_id=j.id
        proc=launch('shared','crash')
        deadline=time.time()+15
        while not (root/'started').exists() and time.time()<deadline:time.sleep(.1)
        assert (root/'started').exists();proc.kill();proc.communicate(timeout=5)
        recovered=launch('shared');out,err=recovered.communicate(timeout=30);assert recovered.returncode==0,err.decode()[-1200:]
        with factory() as s:
            j=s.get(Job,crash_id);assert j.status=='succeeded' and j.checkpoint['saved']=='transcript' and j.checkpoint['starts']==2
        # Actual encoding and library proxy preparation through the same queue.
        folder=root/'projects'/pid;folder.mkdir(parents=True)
        source=folder/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
        from app.timeline import EditPlanV2
        plan=EditPlanV2(segments=[{'id':'source','source_in':0,'duration':30}]).model_dump()
        with factory() as s:
            j=Job(project_id=pid,kind='export',payload={'plan':plan,'revision':1,'aspect_ratio':'9:16'});s.add(j);s.flush();export_id=j.id
            v=VideoClip(title='Fixture');s.add(v);s.flush();asset_id=v.id
            queue.add_library(s,asset_id);s.commit()
        asset_folder=root/'video-clips'/asset_id;asset_folder.mkdir(parents=True)
        import shutil
        shutil.copyfile(source,asset_folder/'source.media')
        proc=launch('media','media');out,err=proc.communicate(timeout=60);assert proc.returncode==0,err.decode()[-1200:]
        with factory() as s:
            assert s.get(Job,export_id).status=='succeeded'
            assert s.get(VideoClip,asset_id).status=='ready'
        assert (folder/(export_id+'.mp4')).exists() and (asset_folder/'proxy.mp4').exists()
        meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(folder/(export_id+'.mp4'))]))
        video=next(x for x in meta['streams'] if x['codec_type']=='video');assert (video['width'],video['height'])==(1080,1920)
        report={'two_process_postgres_lock':True,'fifo_four_jobs':True,'no_duplicate_execution':True,'killed_owner_recovered':True,'checkpoint_retained':True,'real_export_1080x1920':True,'real_library_proxy':True}
        output=Path(__file__).resolve().parents[1]/'storage/qa/queue-postgres-report.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2));print(json.dumps(report))
        engine.dispose()
finally:
    # Exact generated test schema only; never touches public application tables.
    assert schema.startswith('qa_queue_') and len(schema)==41
    with admin.begin() as conn:conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
    admin.dispose()
