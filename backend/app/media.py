import json
import subprocess
import time
from pathlib import Path
from .config import STORAGE
from .editorial import caption_groups

class Cancelled(Exception): pass
def project_dir(project_id):
    from uuid import UUID
    UUID(project_id)
    p = STORAGE / 'projects' / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p
def write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)
def run(args, check=lambda:None):
    import tempfile
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(args, stdout=log, stderr=log)
        try:
            while proc.poll() is None:
                check()
                time.sleep(.3)
            if proc.returncode:
                log.seek(0)
                message = log.read().decode(errors='replace')[-1500:]
                raise RuntimeError(message)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
def probe(path):
    p = subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)], capture_output=True, check=True)
    return json.loads(p.stdout)
def ass_time(seconds):
    t = round(max(0,seconds)*100)
    return f'{t//360000}:{t//6000%60:02}:{t//100%60:02}.{t%100:02}'
def ass_color(color): return '&H00' + color[5:7]+color[3:5]+color[1:3]
def clean_ass(text): return text.replace('\\','').replace('{','').replace('}','').replace('\n',' ')
def subtitles(plan, path):
    s = plan['style']
    lines = ['[Script Info]','ScriptType: v4.00+','PlayResX: 1080','PlayResY: 1920',
      '[V4+ Styles]', 'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
      f"Style: Default,{s['font']},{s['size']},{ass_color(s['highlight'])},{ass_color(s['color'])},&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,{s['outline']},1,2,65,65,{s['margin']},1",
      '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    words = plan['words']
    for group in caption_groups(words):
        start=group[0]['start']; end=group[-1]['end']
        cursor=start; chunks=[]
        for w in group:
            gap=max(0,round((w['start']-cursor)*100))
            if gap: chunks.append('{\\k'+str(gap)+'} ')
            chunks.append('{\\kf'+str(max(1,round((w['end']-w['start'])*100)))+'}'+clean_ass(w['text']).strip()+' ')
            cursor=w['end']
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{''.join(chunks)}")
    path.write_text('\n'.join(lines),encoding='utf-8')

def layout_filter(layout,w,h):
    # Scale before crop so portrait inputs are supported as well as landscape.
    def panel(x,ph):
        return f"scale={w}:{ph}:force_original_aspect_ratio=increase,crop={w}:{ph}:x='max(0,min(iw-ow,iw*{x}-ow/2))':y='(ih-oh)/2',setsar=1"
    if layout['mode']=='fit': return f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1'
    return panel(layout['a'] if layout['mode']=='a' else layout['b'],h)

def render(source,plan,out,preview=False,check=lambda:None):
    # Each layout is rendered independently and concatenated; speaker cuts preserve audio continuity.
    w,h=(360,640) if preview else (1080,1920)
    work=out.parent / (out.stem+'-work'); work.mkdir(exist_ok=True)
    segments=[]
    duration=plan['end']-plan['start']
    for i,layout in enumerate(plan['layouts']):
        check()
        begin=layout['start']; end=plan['layouts'][i+1]['start'] if i+1<len(plan['layouts']) else duration
        target=work/f'{i:03}.mp4'
        args=['ffmpeg','-y','-v','error','-threads','2','-ss',str(plan['start']+begin),'-i',str(source),'-t',str(end-begin)]
        if layout['mode']=='split':
            ph=h//2
            def pane(x): return f"scale={w}:{ph}:force_original_aspect_ratio=increase,crop={w}:{ph}:x='max(0,min(iw-ow,iw*{x}-ow/2))':y='(ih-oh)/2',setsar=1"
            graph=f"[0:v]split=2[a][b];[a]{pane(layout['a'])}[top];[b]{pane(layout['b'])}[bottom];[top][bottom]vstack=inputs=2[v]"
            args+=['-filter_complex_threads','1','-filter_complex',graph,'-map','[v]']
        else: args+=['-vf',layout_filter(layout,w,h)]
        args+=['-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','25' if preview else '20','-pix_fmt','yuv420p','-r','30',str(target)]
        run(args,check); segments.append(target)
    listing=work/'concat.txt'
    listing.write_text('\n'.join(f"file '{p.resolve()}'" for p in segments))
    ass=work/'captions.ass'; subtitles(plan,ass)
    tmp=out.with_suffix('.partial.mp4')
    args=['ffmpeg','-y','-v','error','-filter_threads','1','-f','concat','-safe','0','-i',str(listing),'-ss',str(plan['start']),'-i',str(source),'-t',str(duration),'-map','0:v','-map','1:a:0?', '-vf',f"ass='{ass.resolve()}'",'-c:v','libx264','-threads','2','-preset','veryfast','-crf','25' if preview else '20','-c:a','aac','-b:a','128k','-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)]
    run(args,check); tmp.replace(out)
    import shutil
    shutil.rmtree(work)
