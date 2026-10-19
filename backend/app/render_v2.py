"""Frame-based compositor: cut both AV streams, rasterize overlays, encode final MP4."""
import json,math,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from .media import run,probe
from .timeline import RESOLUTIONS,EditPlanV2
from .config import ROOT

FONTS={'DejaVu Sans':ROOT/'apps/web/public/fonts/EditorDejaVu.ttf','Liberation Sans':ROOT/'apps/web/public/fonts/EditorLiberation.ttf','Poppins':ROOT/'apps/web/public/fonts/Poppins-SemiBold.ttf'}
def text_image(text,style,w,h,words=None,frame=0):
    size=max(1,round(style['size']*w/1080)); font=ImageFont.truetype(str(FONTS[style['font']]),size)
    canvas=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(canvas);maxwidth=style['width']*w
    tokens=[(x['text'],style['highlight'] if style['karaoke'] and frame>=x['start'] else style['color']) for x in words] if words else [(x,style['color']) for x in text.split(' ')]
    lines=[[]];length=0;space=draw.textlength(' ',font=font)
    for token,color in tokens:
        for j,part in enumerate(token.split('\n')):
            if j:lines.append([]);length=0
            n=draw.textlength(part,font=font)
            if lines[-1] and length+space+n>maxwidth:lines.append([]);length=0
            if lines[-1]:length+=space
            lines[-1].append((part,color,n));length+=n
    lineheight=size*1.25;top=style['y']*h-len(lines)*lineheight/2
    for i,line in enumerate(lines):
        width=sum(x[2] for x in line)+space*max(0,len(line)-1)
        x=style['x']*w-width/2 if style['align']=='center' else style['x']*w-maxwidth/2 if style['align']=='left' else style['x']*w+maxwidth/2-width
        for token,color,n in line:
            draw.text((x,top+i*lineheight+size*.1),token,font=font,fill=color,stroke_width=round(style['outline']*w/1080),stroke_fill='#101010',anchor='lt');x+=n+space
    if style['rotation']:canvas=canvas.rotate(-style['rotation'],resample=Image.Resampling.BICUBIC,center=(style['x']*w,style['y']*h))
    if style['opacity']!=1:canvas.putalpha(canvas.getchannel('A').point(lambda p:round(p*style['opacity'])))
    return canvas

def overlay_image(segment,global_style,frame,w,h,folder):
    canvas=Image.new('RGBA',(w,h));items=[]
    for c in segment['captions']:
        if c['start']<=frame<c['end']:items.append((0,c))
    for item in segment['overlays']:
        if item['start']<=frame<item['end']:items.append((item['layer']+1,item))
    for _,item in sorted(items,key=lambda x:x[0]):
        style=item.get('style') or global_style
        if item.get('kind')=='image':
            from uuid import UUID
            aid=str(UUID(item['asset_id']));im=Image.open(folder/'assets'/f'{aid}.png').convert('RGBA')
            im=im.resize((max(1,round(style['width']*w)),max(1,round(style['height']*h))),Image.Resampling.LANCZOS)
            if style['rotation']:im=im.rotate(-style['rotation'],expand=True,resample=Image.Resampling.BICUBIC)
            if style['opacity']!=1:im.putalpha(im.getchannel('A').point(lambda p:round(p*style['opacity'])))
            canvas.alpha_composite(im,(round(style['x']*w-im.width/2),round(style['y']*h-im.height/2)))
        else:canvas.alpha_composite(text_image(item.get('text',''),style,w,h,item.get('words'),frame))
    return canvas

def overlay_movie(plan,work,w,h,folder,check):
    files=[];index=0
    for segment in plan['segments']:
        points={0,segment['duration']}
        for c in segment['captions']:
            points.update((c['start'],c['end']))
            if (c.get('style') or plan['subtitle_style'])['karaoke']:points.update(x['start'] for x in c['words'])
        for o in segment['overlays']:points.update((o['start'],o['end']))
        points=sorted(points)
        for a,b in zip(points,points[1:]):
            check();p=work/f'overlay-{index:05}.png';index+=1
            overlay_image(segment,plan['subtitle_style'],a,w,h,folder).save(p)
            files.extend([f"file '{p.resolve()}'",'option framerate 30',f'duration {(b-a)/30:.12f}'])
    files.extend([files[-3],'option framerate 30']);listing=work/'overlays.txt';listing.write_text('\n'.join(files))
    out=work/'overlays.mov'
    run(['ffmpeg','-y','-v','error','-threads','2','-f','concat','-safe','0','-i',str(listing),'-vf','fps=30','-frames:v',str(sum(s['duration'] for s in plan['segments'])),'-c:v','qtrle','-threads','2','-pix_fmt','argb',str(out)],check)
    return out

def render_v2(source,plan,out,preview=False,check=lambda:None,ratio='9:16'):
    plan=EditPlanV2.model_validate(plan).model_dump();w,h=RESOLUTIONS[ratio]
    if preview:w,h=round(w/3/2)*2,round(h/3/2)*2
    work=out.parent/(out.stem+'-work');work.mkdir(exist_ok=True);parts=[]
    info=probe(source);audio=any(x['codec_type']=='audio' for x in info['streams'])
    for i,s in enumerate(plan['segments']):
        check();t=s['transform'];ph=h//2 if t['mode']=='split' else h
        def pane(x):
            mode='decrease' if t['mode']=='fit' else 'increase'
            sw=math.ceil(w*t['scale']/2)*2;sh=math.ceil(ph*t['scale']/2)*2
            xpos=f'max(0,min(iw-ow,iw*{x}-ow/2))' if t.get('legacy_center') else f'(iw-ow)*{x}'
            return f"format=rgba,scale={sw}:{sh}:force_original_aspect_ratio={mode}:force_divisible_by=2,pad=max(iw\\,{w}):max(ih\\,{ph}):(ow-iw)*{x if not t.get('legacy_center') else .5}:(oh-ih)*{t['y']}:black,crop={w}:{ph}:exact=1:x='{xpos}':y='(ih-oh)*{t['y']}',setsar=1,format=rgba"
        base='fps=30,setpts=PTS-STARTPTS'
        if t['mode']=='split':vf=f'[0:v]{base},split=2[a][b];[a]{pane(t["x"])}[top];[b]{pane(t["b"])}[bottom];[top][bottom]vstack[v]'
        else:vf=f'[0:v]{base},{pane(t["x"])}[v]'
        dur=s['duration']/30;target=work/f'{i:03}.mkv'
        args=['ffmpeg','-y','-v','error','-threads','2','-ss',str(s['source_in']/30),'-i',str(source)]
        if not audio:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        vf+=f';[{"0" if audio else "1"}:a]aresample=48000,asetpts=PTS-STARTPTS,apad,atrim=duration={dur}[aout]'
        args+=['-filter_complex_threads','1','-filter_complex',vf,'-map','[v]','-map','[aout]','-t',str(dur),'-c:v','libx264','-threads','2','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','pcm_s16le','-ar','48000','-ac','2',str(target)]
        run(args,check);parts.append(target)
    listing=work/'parts.txt';listing.write_text('\n'.join(f"file '{p.resolve()}'\nduration {s['duration']/30:.12f}" for p,s in zip(parts,plan['segments'])))
    overlays=overlay_movie(plan,work,w,h,source.parent,check);tmp=out.with_suffix('.partial.mp4');duration=sum(s['duration'] for s in plan['segments'])/30
    inputs=[];filters=['[0:v][1:v]overlay=shortest=1:format=auto,format=yuv420p[v]',f"[0:a]volume={plan['source_volume']}[baseaudio]"];labels=['[baseaudio]'];offset=0
    from uuid import UUID
    for segment in plan['segments']:
        for item in segment['audio']:
            index=2+len(inputs)//2;asset=source.parent/'audio'/f"{str(UUID(item['asset_id']))}.m4a"
            if not asset.is_file():raise RuntimeError('Audio tambahan tidak ditemukan pada proyek ini.')
            inputs+=['-i',str(asset)];label=f'audio{index}'
            a=item['source_in']/30;b=(item['source_in']+item['end']-item['start'])/30;delay=round((offset+item['start'])*1000/30)
            filters.append(f"[{index}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,volume={item['volume']},adelay={delay}:all=1[{label}]");labels.append(f'[{label}]')
        offset+=segment['duration']
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.98:level=0:latency=1[audioout]')
    run(['ffmpeg','-y','-v','error','-threads','2','-f','concat','-safe','0','-i',str(listing),'-i',str(overlays),*inputs,'-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-map','[audioout]','-t',str(duration),'-c:v','libx264','-threads','2','-preset','veryfast','-crf','25' if preview else '20','-c:a','aac','-b:a','160k','-movflags','+faststart',str(tmp)],check)
    tmp.replace(out);shutil.rmtree(work)
