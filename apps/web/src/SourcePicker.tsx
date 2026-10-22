import {useEffect,useRef,useState,type PointerEvent} from 'react';
import {createPortal} from 'react-dom';
import {Play,Pause,SkipBack,SkipForward,X} from 'lucide-react';
import {clamp,timecode,type VideoAsset} from './editorModel';

type RangeProps={asset:VideoAsset;start:number;end:number;onChange:(start:number,end:number)=>void;length?:number;label?:string};

/** Frame-based source selection shared by the studio and collection editor. */
export function SourceRangeEditor({asset,start:a,end:b,onChange,length,label='Bagian sumber'}:RangeProps){
 const video=useRef<HTMLVideoElement>(null),strip=useRef<HTMLDivElement>(null),dragCleanup=useRef<(()=>void)|null>(null);
 const [frame,setFrame]=useState(a),[playing,setPlaying]=useState(false),[zoom,setZoom]=useState(30),[width,setWidth]=useState(600);
 const stripWidth=Math.max(width,asset.duration*zoom),pixels=stripWidth/Math.max(1,asset.frames),count=Math.min(100,Math.ceil(stripWidth/80));
 useEffect(()=>{const node=strip.current;if(!node)return;const resize=new ResizeObserver(entries=>setWidth(Math.max(300,entries[0].contentRect.width)));resize.observe(node);return()=>resize.disconnect()},[]);
 useEffect(()=>()=>dragCleanup.current?.(),[]);
 function seek(value:number){const next=clamp(Math.round(value),0,Math.max(0,asset.frames-1));setFrame(next);if(video.current)video.current.currentTime=next/30}
 function choose(start:number,end:number){onChange(start,end);seek(start)}
 function drag(event:PointerEvent,kind:'move'|'start'|'end'){
  event.preventDefault();event.stopPropagation();dragCleanup.current?.();
  const baseA=a,baseB=b,x=event.clientX;
  const move=(ev:globalThis.PointerEvent)=>{const delta=Math.round((ev.clientX-x)/pixels);if(kind==='move'){const next=clamp(baseA+delta,0,asset.frames-(baseB-baseA));choose(next,next+baseB-baseA)}else if(kind==='start')choose(clamp(baseA+delta,0,baseB-1),baseB);else choose(baseA,clamp(baseB+delta,baseA+1,asset.frames))};
  const finish=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',finish);window.removeEventListener('pointercancel',finish);dragCleanup.current=null};
  dragCleanup.current=finish;window.addEventListener('pointermove',move);window.addEventListener('pointerup',finish);window.addEventListener('pointercancel',finish);
 }
 function toggle(){if(playing){video.current?.pause();setPlaying(false)}else{if(frame<a||frame>=b)seek(a);void video.current?.play().then(()=>setPlaying(true)).catch(()=>setPlaying(false))}}
 const step=(edge:'start'|'end',key:string,shift:boolean)=>{const amount=(key==='ArrowRight'?1:-1)*(shift?30:1);if(edge==='start')choose(clamp(a+amount,0,b-1),b);else choose(a,clamp(b+amount,a+1,asset.frames))};
 return <div className="source-editor">
  <video ref={video} src={asset.proxy_url} poster={asset.thumbnail_url} muted playsInline preload="metadata" aria-label={'Preview '+asset.title} onLoadedMetadata={()=>seek(a)} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)} onTimeUpdate={e=>{const next=Math.round(e.currentTarget.currentTime*30);setFrame(next);if(playing&&next>=b){e.currentTarget.pause();seek(a)}}}/>
  <div className="source-transport"><span className="timecode">{timecode(frame)}</span><button type="button" title="Mundur satu frame" aria-label="Sumber mundur satu frame" onClick={()=>seek(frame-1)}><SkipBack size={17}/></button><button type="button" className="source-play" title={playing?'Jeda pilihan':'Putar pilihan'} aria-label={playing?'Jeda pilihan':'Putar pilihan'} onClick={toggle}>{playing?<Pause size={18}/>:<Play size={18}/>}</button><button type="button" title="Maju satu frame" aria-label="Sumber maju satu frame" onClick={()=>seek(frame+1)}><SkipForward size={17}/></button><span className="timecode">{timecode(asset.frames)}</span><label>Zoom<input aria-label="Zoom sumber" type="range" min={8} max={100} value={zoom} onChange={e=>setZoom(+e.target.value)}/></label></div>
  <div className="source-scroll" ref={strip}><div className="source-strip" style={{width:stripWidth}} onClick={e=>{if(e.target!==e.currentTarget)return;const position=Math.round((e.clientX-e.currentTarget.getBoundingClientRect().left)/pixels),span=b-a,next=clamp(position,0,asset.frames-span);choose(next,next+span)}}>
   {Array.from({length:count},(_,i)=><img alt="" draggable={false} key={i} style={{left:i*stripWidth/count,width:stripWidth/count}} src={asset.thumbnail_base+String(Math.floor(i*asset.duration/count)+1).padStart(5,'0')+'.jpg'}/>)}
   <div className="source-range" role="slider" tabIndex={0} aria-label={label} aria-valuemin={0} aria-valuemax={Math.max(0,asset.frames-(b-a))} aria-valuenow={a} aria-valuetext={timecode(a)+' sampai '+timecode(b)} style={{left:a*pixels,width:Math.max(8,(b-a)*pixels)}} onPointerDown={e=>drag(e,'move')} onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.key==='Home'||e.key==='End'){e.preventDefault();const next=e.key==='Home'?0:Math.max(0,asset.frames-(b-a));choose(next,next+b-a);return}if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const next=clamp(a+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?30:1),0,asset.frames-(b-a));choose(next,next+b-a)}}}>
    {!length&&<><button type="button" title="Tarik untuk mengubah awal adegan" aria-label="Awal adegan" onPointerDown={e=>drag(e,'start')} onKeyDown={e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();e.stopPropagation();step('start',e.key,e.shiftKey)}}}/><button type="button" title="Tarik untuk mengubah akhir adegan" aria-label="Akhir adegan" onPointerDown={e=>drag(e,'end')} onKeyDown={e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();e.stopPropagation();step('end',e.key,e.shiftKey)}}}/></>}
    <span>{timecode(a)} — {timecode(b)}</span>
   </div>
  </div></div>
 </div>
}

export function SourcePicker({asset,length,initial=0,onCancel,onUse}:{asset:VideoAsset;length?:number;initial?:number;onCancel:()=>void;onUse:(a:number,b:number)=>void}){
 const dialog=useRef<HTMLDialogElement>(null),[start,setStart]=useState(clamp(initial,0,Math.max(0,asset.frames-(length||30)))),[end,setEnd]=useState(Math.min(asset.frames,initial+(length||Math.min(150,asset.frames))));
 const valid=end>start&&(!length||end-start===length)&&end<=asset.frames;
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close()},[]);
 return createPortal(<dialog ref={dialog} className="source-modal" aria-label="Pilih bagian sumber" onCancel={e=>{e.preventDefault();onCancel()}}><header><div><h2>{asset.title}</h2><p>{length?'Slot tetap '+timecode(length)+' · Geser area pilihan untuk memilih bagian lain.':'Pilih rentang adegan dengan menarik kedua tepi area pilihan.'}</p></div><button type="button" title="Tutup" onClick={onCancel} aria-label="Tutup pemilih sumber"><X size={20}/></button></header><SourceRangeEditor asset={asset} start={start} end={end} length={length} onChange={(a,b)=>{setStart(a);setEnd(b)}}/><footer><span>Sumber {timecode(start)}–{timecode(end)} · {timecode(end-start)}</span><button type="button" onClick={onCancel}>Batal</button><button type="button" className="primary" disabled={!valid} onClick={()=>onUse(start,end)}>Gunakan bagian ini</button></footer>{!valid&&<p role="alert">Video lebih pendek dari slot. Pilih video lain atau pendekkan slot.</p>}</dialog>,document.body)
}
