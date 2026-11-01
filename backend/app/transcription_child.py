"""Long-lived, bounded-audio Whisper subprocess; stdin/stdout carry local commands."""
import ctypes,json,os,signal,sys
from pathlib import Path

def main():
    # If the owning worker is killed, this child must stop before another owner runs.
    parent=int(os.environ.get('VC_PARENT_PID',os.getppid()))
    ctypes.CDLL(None).prctl(1,signal.SIGTERM)
    if os.getppid()!=parent:return
    from .config import settings,STORAGE
    from faster_whisper import WhisperModel
    model=WhisperModel(os.environ.get('VC_WHISPER_MODEL',settings.whisper_model),device='cpu',compute_type='int8',cpu_threads=settings.whisper_threads,download_root=str(STORAGE/'models'))
    print(json.dumps({'event':'ready'}),flush=True)
    for line in sys.stdin:
        request=json.loads(line)
        try:
            segments,info=model.transcribe(request['audio'],language=request.get('language'),word_timestamps=True,vad_filter=True,hotwords=request.get('hotwords'),initial_prompt=request.get('hotwords'))
            words=[{'start':w.start,'end':w.end,'text':w.word.strip(),'probability':w.probability} for seg in segments for w in (seg.words or []) if w.end>w.start and w.word.strip()]
            print(json.dumps({'event':'result','index':request['index'],'language':info.language if words else request.get('language'),'words':words}),flush=True)
        except Exception as error:
            print(json.dumps({'event':'error','type':type(error).__name__}),flush=True)
            return

if __name__=='__main__':main()
