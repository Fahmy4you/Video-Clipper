"""Pure transition/fade arithmetic shared by export and tested against preview."""
import json,math
from .video_library import folder
from .media import run

def fade_expr(fade,length):
    span=fade.get('span') or length;offset=fade.get('offset',0);a=min(fade.get('in_frames',0),span);b=min(fade.get('out_frames',0),span)
    x=f'(t*30+{offset})'
    return f'max(0,min(1,min({x}/{a}'+f',({span}-{x})/{b})))' if a and b else f'max(0,min(1,{x}/{a}))' if a else f'max(0,min(1,({span}-{x})/{b}))' if b else '1'
def limits(item,items,duration,frames):
    ordered=sorted(items,key=lambda b:b['start']);i=ordered.index(item);prev=ordered[i-1]['end'] if i else 0;nxt=ordered[i+1]['start'] if i+1<len(ordered) else duration
    result=[]
    for enter,edge in [(True,item['transition_in']),(False,item['transition_out'])]:
        half=math.floor(min(edge['frames']/2,(item['end']-item['start'])/2,(item['start']-prev)/2 if enter else (nxt-item['end'])/2))
        kind=edge['kind']
        if kind=='crossfade' and (item['source_in']<half if enter else item['source_in']+item['end']-item['start']+half>frames):kind='black'
        result.append((kind,half if kind!='none' else 0))
    return result

def composite(base,segment,out,w,h,check):
    items=segment.get('broll',[])
    if not items:return base
    args=['ffmpeg','-y','-v','error','-threads','2','-i',str(base)]
    filters=['[0:v]fps=30,settb=1/30,setpts=N,format=yuv420p[base]'];current='base';duration=segment['duration']
    for idx,item in enumerate(items,1):
        root=folder(item['asset_id']);meta=json.loads((root/'metadata.json').read_text());(ki,hi),(ko,ho)=limits(item,items,duration,meta['frames'])
        pre=min(item['source_in'],math.ceil(hi));src=(item['source_in']-pre)/30;delay=(item['start']-pre)/30
        args+=['-ss',str(src),'-i',str(root/'source.media')];t=item['transform'];scale=t['scale'];mode='decrease' if t['mode']=='fit' else 'increase'
        vf=f"fps=30,settb=1/30,setpts=N,scale={round(w*scale/2)*2}:{round(h*scale/2)*2}:force_original_aspect_ratio={mode}:force_divisible_by=2,pad=max(iw\\,{w}):max(ih\\,{h}):(ow-iw)*{t['x']}:(oh-ih)*{t['y']}:black,crop={w}:{h}:(iw-ow)*{t['x']}:(ih-oh)*{t['y']},setsar=1,tpad=start_duration={delay}:start_mode=clone:stop_duration={duration/30}:stop_mode=clone,trim=duration={duration/30},settb=1/30,setpts=N,format=yuva420p"
        a=item['start'];b=item['end']
        # Native alpha fades are evaluated once per frame, rather than a complex
        # expression for every RGB pixel. Black mattes affect only the base image.
        for label,kind,half,start,end,fade in [
            ('in',ki,hi,a-hi,a+hi,f'fade=t=in:st={(a-hi)/30}:d={hi/30}:alpha=1'),
            ('out',ko,ho,b-ho,b+ho,f'fade=t=out:st={b/30}:d={ho/30}:alpha=1')]:
            if kind=='black' and half:
                mask=f'mask{idx}{label}';dest=f'dark{idx}{label}'
                filters.append(f'color=c=black:s={w}x{h}:r=30:d={duration/30},format=yuva420p,{fade}[{mask}]')
                filters.append(f"[{current}][{mask}]overlay=enable='gte(t,{start/30})*lt(t,{end/30})':shortest=1[{dest}]");current=dest
        if hi:vf+=f",fade=t=in:st={(a-hi if ki=='crossfade' else a)/30}:d={(2*hi if ki=='crossfade' else hi)/30}:alpha=1"
        if ho:vf+=f",fade=t=out:st={(b-ho)/30}:d={(2*ho if ko=='crossfade' else ho)/30}:alpha=1"
        filters.append(f'[{idx}:v]{vf}[b{idx}]')
        start=(a-hi if ki=='crossfade' else a)/30;end=(b+ho if ko=='crossfade' else b)/30
        filters.append(f"[{current}][b{idx}]overlay=enable='gte(t,{start})*lt(t,{end})':shortest=1[v{idx}]");current=f'v{idx}'
    run(args+['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map',f'[{current}]','-map','0:a','-t',str(duration/30),'-c:v','libx264','-threads','2','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','copy',str(out)],check);return out
