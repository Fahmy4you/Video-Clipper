"""Small-model highlight pass with bounded child memory and atomic source-range caches."""
import hashlib,json,math
from copy import deepcopy
from .transcription import Child,source_identity,release_source_cache,TranscriptionFailure,merge_words
from .media import run,write_json,Cancelled
from .timeline import stable,EditPlanV2
from .editorial import caption_groups
from sqlalchemy.exc import SQLAlchemyError
MODEL='small'
def context_hotwords(source,start,end):
    # Hints come from the surrounding source transcript, never from B-roll descriptions.
    try:
        transcript=json.loads((source.parent/'transcript.json').read_text())
        text=' '.join(w['text'] for w in transcript['words'] if w['end']>=start-30 and w['start']<=end+30).casefold()
    except (OSError,ValueError,KeyError,TypeError):return None
    families=[(('emas','tambang','tabang'),'mining emas, tambang emas, penambangan emas'),(('bitcoin','kripto','crypto'),'Bitcoin, kripto'),(('blockchain',),'blockchain'),(('nft',),'NFT'),(('trading','trader'),'trading, trader'),(('investasi',),'investasi'),(('saham',),'saham')]
    hints=[hint for triggers,hint in families if any(word in text for word in triggers)]
    return ', '.join(hints) or None

def refine(source,duration,spans,check=lambda:None,update=lambda **kw:None,jid=None,language=None):
    identity=source_identity(source);root=source.parent/'subtitle-refinement';root.mkdir(exist_ok=True)
    # One persisted budget per job, so a worker crash cannot retry the same part forever.
    budget_path=root/(str(jid or 'manual')+'-attempts.json')
    try:budget=json.loads(budget_path.read_text())
    except (OSError,ValueError):budget={}
    results=[];child=None;peak=0
    # No more than 120 seconds of core audio is loaded at once.
    parts=[]
    merged=[]
    for a,b in sorted(set((round(a,4),round(b,4)) for a,b in spans)):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    for start,end in merged:
        for i in range(math.ceil((end-start)/120)):
            a=start+i*120;b=min(end,a+120)
            parts.append((a,b))
    try:
        for index,(a,b) in enumerate(parts):
            check();hotwords=context_hotwords(source,a,b);spec={'version':3,'source':identity,'model':MODEL,'compute':'int8','threads':2,'start':a,'end':b,'context':2,'language':language,'hotwords':hotwords}
            key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest();path=root/(key+'.json')
            saved=None
            try:
                saved=json.loads(path.read_text())
                if saved['identity']!=spec: saved=None
                else:
                    from .schemas import Word
                    for w in saved['words']:Word.model_validate(w)
            except (OSError,ValueError,KeyError,TypeError):saved=None
            update(stage=f'Memeriksa subtitle {index+1}/{len(parts)}',progress=82+int(7*index/max(1,len(parts))),metrics={'subtitle_completed':index,'subtitle_total':len(parts),'subtitle_model':MODEL})
            if saved:
                results.append(saved['words']);language=language or saved.get('language');peak=max(peak,saved.get('peak_memory_bytes',0));continue
            audio=root/(key+'.wav');input_start=max(0,a-2);input_end=min(duration,b+2)
            attempts=budget.get(key,0)
            if attempts>=2:raise TranscriptionFailure('Bagian subtitle ini telah gagal dua kali. Gunakan Coba lagi untuk memulai percobaan baru.')
            for attempt in range(attempts,2):
                try:
                    check();budget[key]=attempt+1;write_json(budget_path,budget)
                    if child is None:
                        update(stage='Menyiapkan Whisper small untuk subtitle')
                        child=Child(check,lambda metrics:update(metrics=metrics),jid,model=MODEL);child.wait('ready')
                    run(['ffmpeg','-y','-v','error','-ss',str(input_start),'-i',str(source),'-t',str(input_end-input_start),'-vn','-ac','1','-ar','16000',str(audio)],check)
                    release_source_cache(source);response=child.transcribe(audio,index,language,hotwords);peak=max(peak,child.peak)
                    words=[]
                    for w in response['words']:
                        start=w['start']+input_start;end=w['end']+input_start
                        if not math.isfinite(start+end) or not a<=(start+end)/2<b or end<=start:continue
                        start=max(a,start);end=min(b,end)
                        if end>start:words.append({'start':round(start,4),'end':round(end,4),'text':w['text'],'probability':w.get('probability')})
                    language=language or (response.get('language') if words else None)
                    # Language discovery does not alter the key of this completed part.
                    write_json(path,{'identity':spec,'words':words,'language':language,'peak_memory_bytes':peak})
                    results.append(words);break
                except (Cancelled,SQLAlchemyError):
                    budget[key]=max(0,budget.get(key,1)-1);write_json(budget_path,budget);raise
                except TranscriptionFailure:
                    if child:child.close();child=None
                    if attempt:raise
                finally:audio.unlink(missing_ok=True)
        words=merge_words(results)
        update(metrics={'subtitle_completed':len(parts),'subtitle_total':len(parts),'subtitle_model':MODEL,'peak_memory_bytes':peak})
        return {'words':words,'model':MODEL,'language':language,'peak_memory_bytes':peak}
    finally:
        if child:child.close()

def segment_words(segment,words):
    start=segment['source_in'];end=start+segment['duration'];out=[]
    for w in words:
        a=max(0,round(w['start']*30)-start);b=min(segment['duration'],round(w['end']*30)-start)
        if not start<=(w['start']+w['end'])*15<end or b<=a:continue
        out.append({'id':stable(f"refined-{start+a}-{start+b}-{w['text']}"),'start':a,'end':b,'text':w['text'],'probability':w.get('probability'),'timing_estimated':False})
    return out

def fresh_captions(segment,words):
    ws=segment_words(segment,words);out=[]
    for i,g in enumerate(caption_groups([dict(w,start=w['start']/30,end=w['end']/30) for w in ws])):
        group=[dict(w,start=round(w['start']*30),end=round(w['end']*30)) for w in g]
        out.append({'id':stable(f"refined-caption-{segment['id']}-{i}"),'start':group[0]['start'],'end':group[-1]['end'],'words':group,'style':None})
    return out

def review(plan,words):
    proposals=[];offset=0
    for segment in plan['segments']:
        assigned={c['id']:[] for c in segment['captions']}
        for word in segment_words(segment,words):
            mid=(word['start']+word['end'])/2
            candidates=[c for c in segment['captions'] if c['start']-6<=mid<c['end']+6]
            if not candidates:continue # Do not resurrect deliberately deleted captions.
            cap=min(candidates,key=lambda c:abs(mid-(c['start']+c['end'])/2));assigned[cap['id']].append(word)
        for cap in segment['captions']:
            ws=assigned[cap['id']]
            if not ws:continue # Silence/uncertainty must not erase an existing correction.
            proposed={**deepcopy(cap),'start':ws[0]['start'],'end':ws[-1]['end'],'words':ws}
            proposals.append({'segment_id':segment['id'],'caption_id':cap['id'],'frame':offset+cap['start'],'before':' '.join(w['text'] for w in cap['words']),'after':' '.join(w['text'] for w in ws),'caption':proposed,'needs_review':any((w.get('probability') or 0)<.6 for w in ws)})
        offset+=segment['duration']
    return proposals

def apply_review(plan,proposals,accepted):
    result=deepcopy(plan);lookup={(p['segment_id'],p['caption_id']):p['caption'] for p in proposals if p['caption_id'] in accepted}
    for segment in result['segments']:
        segment['captions']=[deepcopy(lookup.get((segment['id'],c['id']),c)) for c in segment['captions']]
    return EditPlanV2.model_validate(result).model_dump()
