import json, subprocess, urllib.request
from pathlib import Path
from faster_whisper import WhisperModel
pid='a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07'
folder=Path('storage/projects')/pid
qa=Path('storage/qa/video-test'); qa.mkdir(exist_ok=True,parents=True)
with urllib.request.urlopen('http://localhost:8000/api/projects/'+pid+'/clips') as r: clips=json.load(r)
print('Preparing higher-accuracy model for selected clips',flush=True)
model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=2,download_root='storage/models')
for i,c in enumerate(clips):
    plan=c['plan']; audio=qa/f'clip-{i+1}.wav'
    subprocess.run(['ffmpeg','-y','-v','error','-ss',str(plan['start']),'-i',str(folder/'audio.wav'),'-t',str(plan['end']-plan['start']),str(audio)],check=True)
    segs,info=model.transcribe(str(audio),language='id',word_timestamps=True,vad_filter=True,initial_prompt='Percakapan podcast Indonesia. Trading crypto, sistem trading, mentalitas judi, risk management, konsisten profit, defensive, offensive, home run, Mobile Legends, Akademi Crypto.')
    words=[{'start':w.start,'end':min(w.end,plan['end']-plan['start']),'text':w.word.strip()} for s in segs for w in (s.words or []) if w.end>w.start and w.start<plan['end']-plan['start']]
    (qa/f'clip-{i+1}-words.json').write_text(json.dumps(words,ensure_ascii=False,indent=2))
    print(c['id'], ' '.join(w['text'] for w in words),flush=True)
print('Refinement ready for review',flush=True)
