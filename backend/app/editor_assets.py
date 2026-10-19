import json,subprocess,array,sys
from pathlib import Path
from .media import run,write_json,probe
def prepare_editor(folder,check=lambda:None):
    root=folder/'editor';root.mkdir(exist_ok=True);source=folder/'source.mp4';proxy=root/'proxy.mp4'
    if not proxy.exists():
        temp=root/'proxy.partial.mp4'
        run(['ffmpeg','-y','-v','error','-threads','2','-i',str(source),'-vf','scale=960:540:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','28','-g','15','-c:a','aac','-b:a','96k','-movflags','+faststart',str(temp)],check);temp.replace(proxy)
    thumb=root/'thumbs';thumb.mkdir(exist_ok=True)
    if not (root/'manifest.json').exists():
        run(['ffmpeg','-y','-v','error','-threads','2','-i',str(proxy),'-vf','fps=1/5,scale=160:90:force_original_aspect_ratio=decrease,pad=160:90:(ow-iw)/2:(oh-ih)/2','-q:v','5',str(thumb/'%05d.jpg')],check)
        data=subprocess.check_output(['ffmpeg','-v','error','-i',str(source),'-vn','-ac','1','-ar','8000','-f','s16le','-'])
        samples=array.array('h');samples.frombytes(data)
        if sys.byteorder!='little':samples.byteswap()
        peaks=[round(max((abs(v) for v in samples[i:i+800]),default=0)/32768,4) for i in range(0,len(samples),800)]
        meta=probe(proxy);v=next(x for x in meta['streams'] if x['codec_type']=='video')
        write_json(root/'manifest.json',{'status':'ready','width':v['width'],'height':v['height'],'thumbnail_interval':5,'thumbnail_count':len(list(thumb.glob('*.jpg'))),'waveform_interval':.1,'waveform':peaks})
    return {'message':'Media editor siap.'}
