"""Project-owned audio import and extraction, executed by the worker."""
import json,math,re,shutil,subprocess
from pathlib import Path
from uuid import UUID
from urllib.parse import urlparse
import numpy as np
from pydantic import BaseModel,Field,field_validator
from typing import Literal
from .schemas import youtube_url
from .media import run,write_json,Cancelled

MAX_BYTES=200*1024*1024
MAX_SECONDS=1800
class AudioImport(BaseModel):
    model_config={'extra':'forbid'}
    trim_end_seconds:float=Field(default=0,ge=0,le=10,allow_inf_nan=False)
    platform:Literal['youtube','tiktok']
    url:str=Field(max_length=2048)
    @field_validator('url')
    @classmethod
    def valid_url(cls,value,info):
        return audio_url(value,info.data.get('platform'))

def audio_url(value,platform):
    if platform=='youtube':return youtube_url(value)
    u=urlparse(value.strip());host=(u.hostname or '').lower()
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443):raise ValueError('Gunakan URL HTTPS TikTok yang valid.')
    valid=(host in ('www.tiktok.com','tiktok.com','m.tiktok.com') and re.fullmatch(r'/@[^/]+/video/[0-9]+/?',u.path)) or (host in ('vm.tiktok.com','vt.tiktok.com') and re.fullmatch(r'/[A-Za-z0-9]+/?',u.path))
    if not valid:raise ValueError('Masukkan URL satu video TikTok publik, bukan profil atau playlist.')
    return u._replace(fragment='').geturl()

def audio_metadata(folder,aid):
    aid=str(UUID(aid));path=folder/'audio'/f'{aid}.json'
    if not path.is_file() or not (folder/'audio'/f'{aid}.m4a').is_file():raise ValueError('Audio tidak ditemukan pada proyek ini.')
    return json.loads(path.read_text())

def normalize_audio(source,folder,aid,name,origin,check=lambda:None,require_video=False,trim_end_seconds=0):
    aid=str(UUID(aid));dest=folder/'audio';dest.mkdir(exist_ok=True)
    try:
        probe=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(source)],capture_output=True,check=True,timeout=30)
        info=json.loads(probe.stdout)
    except Exception:raise RuntimeError('File tidak dapat dibaca. Gunakan file audio atau video yang valid.') from None
    if not any(x['codec_type']=='audio' for x in info['streams']):raise RuntimeError('File ini tidak memiliki audio.')
    if require_video and not any(x['codec_type']=='video' for x in info['streams']):raise RuntimeError('Pilih file video untuk fitur ekstrak video.')
    duration=float(info['format'].get('duration',0))
    if not math.isfinite(duration) or not 0<duration<=MAX_SECONDS:raise RuntimeError('Durasi audio maksimal 30 menit.')
    kept_duration=duration-trim_end_seconds
    if kept_duration<1/30:raise RuntimeError('Potongan akhir terlalu panjang. Kurangi durasi closing yang dibuang.')
    temp=dest/f'{aid}.partial.m4a';out=dest/f'{aid}.m4a';raw=dest/f'{aid}.pcm'
    try:
        run(['ffmpeg','-y','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:a:0','-vn','-t',str(kept_duration),'-ac','2','-ar','48000','-c:a','aac','-b:a','192k','-threads','2',str(temp)],check)
        run(['ffmpeg','-y','-v','error','-i',str(temp),'-vn','-ac','1','-ar','4000','-f','f32le',str(raw)],check)
        samples=np.fromfile(raw,dtype='<f4');duration=len(samples)/4000;interval=max(.1,duration/2000);step=max(1,round(interval*4000))
        waveform=[round(float(np.max(np.abs(samples[i:i+step]))),3) for i in range(0,len(samples),step)]
        result={'id':aid,'name':name[:200],'duration':duration,'frames':math.floor(duration*30),'url':f'/api/audio/{folder.name}/{aid}','waveform':waveform,'waveform_interval':interval,'origin':origin,'trim_end_seconds':trim_end_seconds,'original_duration':float(info['format'].get('duration',0))}
        check();temp.replace(out);write_json(dest/f'{aid}.json',result);return result
    finally:
        temp.unlink(missing_ok=True);raw.unlink(missing_ok=True)

def import_audio(folder,payload,check=lambda:None,progress=lambda text,value:None):
    aid=str(UUID(payload['asset_id']))
    try:return audio_metadata(folder,aid)
    except ValueError:pass
    if payload['mode'] in ('audio','video'):
        source=folder/'audio-inbox'/f'{aid}.media'
        if not source.is_file():raise RuntimeError('File unggahan tidak tersedia. Unggah ulang file audio/video.')
        progress('Mengekstrak dan menyiapkan audio',30)
        result=normalize_audio(source,folder,aid,payload['name'],'upload',check,payload['mode']=='video');source.unlink();return result
    url=audio_url(payload['url'],payload['platform']);work=folder/'audio-inbox'/aid;work.mkdir(parents=True,exist_ok=True)
    try:
        import yt_dlp
        def hook(data):
            check()
            if data.get('downloaded_bytes',0)>MAX_BYTES:raise RuntimeError('Unduhan audio melebihi 200 MB.')
        options={'format':('best[vcodec!=none][acodec!=none][format_id!^=download][format_note!*=?"watermarked"]' if payload['platform']=='tiktok' else 'bestaudio/best'),'outtmpl':str(work/'source.%(ext)s'),'noplaylist':True,'quiet':True,'no_warnings':True,'socket_timeout':20,'retries':2,'max_filesize':MAX_BYTES,'progress_hooks':[hook],'js_runtimes':{'node':{}}}
        if payload['platform']=='tiktok':
            from yt_dlp.networking.impersonate import ImpersonateTarget
            options['impersonate']=ImpersonateTarget(client='chrome')
        progress('Mengambil video TikTok' if payload['platform']=='tiktok' else 'Mengambil audio YouTube',10)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info=ydl.extract_info(url,download=False)
                if info.get('_type') in ('playlist','multi_video') or info.get('is_live'):raise RuntimeError('Playlist dan live belum didukung.')
                if not info.get('duration') or info['duration']>MAX_SECONDS:raise RuntimeError('Video untuk audio maksimal 30 menit.')
                ydl.download([url])
        except (Cancelled,RuntimeError):raise
        except Exception:raise RuntimeError('Audio tidak dapat diambil. Pastikan video publik dan URL benar; penyedia mungkin membatasi unduhan. Kamu juga bisa mengunggah file lokal.') from None
        candidates=[p for p in work.glob('source.*') if p.suffix not in ('.part','.ytdl','.json')]
        if len(candidates)!=1:raise RuntimeError('Berkas audio hasil unduhan tidak ditemukan atau melebihi batas ukuran.')
        progress('Mengekstrak dan menyiapkan audio',65)
        return normalize_audio(candidates[0],folder,aid,info.get('title') or 'Audio '+payload['platform'],payload['platform'],check,require_video=payload['platform']=='tiktok',trim_end_seconds=payload.get('trim_end_seconds',0) if payload['platform']=='tiktok' else 0)
    finally:shutil.rmtree(work,ignore_errors=True)

