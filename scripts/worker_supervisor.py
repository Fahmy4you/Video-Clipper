"""Bounded worker restarts; API and frontend remain available after a worker crash."""
import json,os,signal,subprocess,time
from collections import deque
from pathlib import Path

class RestartPolicy:
    def __init__(self):self.restarts=deque()
    def delay(self,tick):
        while self.restarts and self.restarts[0]<tick-600:self.restarts.popleft()
        if len(self.restarts)>=3:return None
        delay=(5,15,30)[len(self.restarts)];self.restarts.append(tick);return delay

class WorkerSupervisor:
    def __init__(self,args,env,logs,runtime):
        self.args=args;self.env=env;self.logs=logs;self.runtime=runtime;self.runtime.parent.mkdir(parents=True,exist_ok=True)
        self.log=(logs/'worker.log').open('a');self.child=None;self.policy=RestartPolicy();self.next_start=None;self.blocked=False;self.last_write=0;self.status='starting';self.message='Menyiapkan worker.';self.last_memory=0;self.peak_memory=0
    def write(self):
        value={'updated':time.time(),'status':self.status,'message':self.message,'pid':self.child.pid if self.child and self.child.poll() is None else None,'restart_count':len(self.policy.restarts),'next_restart_at':self.next_start,'memory_bytes':self.last_memory,'peak_memory_bytes':self.peak_memory}
        tmp=self.runtime.with_suffix('.tmp');tmp.write_text(json.dumps(value));tmp.replace(self.runtime);self.last_write=time.monotonic()
    def start(self):
        self.child=subprocess.Popen(self.args,env=self.env,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        self.status='ready';self.message='Worker aktif.';self.next_start=None;self.write()
    def tick(self):
        if self.child and self.child.poll() is None:
            try:
                rss=next(line for line in Path('/proc/'+str(self.child.pid)+'/status').read_text().splitlines() if line.startswith('VmRSS:'))
                self.last_memory=int(rss.split()[1])*1024;self.peak_memory=max(self.peak_memory,self.last_memory)
            except (OSError,StopIteration):pass
        if self.child and self.child.poll() is not None:
            code=self.child.returncode;self.child=None;delay=self.policy.delay(time.monotonic())
            record={'event':'worker_exit','exit_code':code,'signal':-code if code<0 else None,'restart_delay':delay,'time':time.time(),'memory_bytes':self.last_memory,'peak_memory_bytes':self.peak_memory}
            self.log.write(json.dumps(record)+'\n');self.log.flush();print(json.dumps(record),flush=True)
            if delay is None:self.blocked=True;self.status='unavailable';self.message='Worker berhenti berulang kali. Periksa storage/logs/worker.log lalu jalankan ulang launcher.'
            else:self.next_start=time.time()+delay;self.status='restarting';self.message='Worker berhenti; memulihkan dalam '+str(delay)+' detik. Halaman dan draft tetap tersedia.'
            self.write()
        if not self.blocked and self.child is None and self.next_start and time.time()>=self.next_start:self.start()
        if time.monotonic()-self.last_write>=3:self.write()
    def stop(self):
        if self.child and self.child.poll() is None:
            os.killpg(self.child.pid,signal.SIGTERM)
            try:self.child.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(self.child.pid,signal.SIGKILL);self.child.wait()
        self.status='unavailable';self.message='Launcher dihentikan. Jalankan npm run dev untuk melanjutkan.';self.write();self.log.close()
