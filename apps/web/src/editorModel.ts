export type Ratio='9:16'|'16:9'|'1:1'|'4:5'|'4:3';
export const formats:{id:Ratio;width:number;height:number;label:string;hint:string}[]=[{id:'9:16',width:1080,height:1920,label:'Vertikal',hint:'TikTok · Shorts · Reels · Story'},{id:'16:9',width:1920,height:1080,label:'Horizontal',hint:'YouTube · TV'},{id:'1:1',width:1080,height:1080,label:'Persegi',hint:'Instagram · Facebook'},{id:'4:5',width:1080,height:1350,label:'Portrait',hint:'Feed Instagram'},{id:'4:3',width:1440,height:1080,label:'Klasik',hint:'Format televisi klasik'}];
export type Style={x:number;y:number;width:number;height:number;rotation:number;opacity:number;font:'DejaVu Sans'|'Liberation Sans'|'Poppins';size:number;color:string;highlight:string;outline:number;align:'left'|'center'|'right';karaoke:boolean};
export type Word={id:string;start:number;end:number;text:string};
export type Caption={id:string;start:number;end:number;words:Word[];style:Style|null};
export type Overlay={id:string;kind:'text'|'image';start:number;end:number;text:string;asset_id:string|null;layer:number;style:Style};
export type AudioItem={id:string;asset_id:string;start:number;end:number;source_in:number;volume:number};
export type AudioAsset={id:string;name:string;duration:number;frames:number;url:string;waveform:number[];waveform_interval:number;origin:string};
export type Segment={id:string;source_in:number;duration:number;transform:{legacy_center?:boolean;mode:'fit'|'fill'|'split';x:number;y:number;scale:number;b:number};captions:Caption[];overlays:Overlay[];excluded_word_ids:string[];audio?:AudioItem[]};
export type Plan={source_volume?:number;version:2;fps:30;segments:Segment[];subtitle_style:Style};
export type Clip={id:string;project_id:string;title:string;reason:string;revision:number;fulfills_prompt:boolean;plan:Plan};
export type Project={id:string;url:string;title:string;duration:number;status:string;created_at:string;gemini_model:string|null;aspect_ratio:Ratio;highlight_count:number;additional_prompt:string;analysis_report:{requested?:number;generated?:number;unmet_requests?:string[]}};
export type SourceWord={start:number;end:number;text:string};
export type Asset={id:string;name:string;width:number;height:number;url:string};
export type Manifest={status:string;proxy_url?:string;thumbnail_base?:string;thumbnail_interval?:number;thumbnail_count?:number;waveform?:number[];waveform_interval?:number;width?:number;height?:number};
export const uid=()=>crypto.randomUUID();
export const clamp=(v:number,a:number,b:number)=>Math.max(a,Math.min(b,v));
export const style=():Style=>({x:.5,y:.84,width:.88,height:.2,rotation:0,opacity:1,font:'DejaVu Sans',size:62,color:'#FFFFFF',highlight:'#5EEAD4',outline:3,align:'center',karaoke:true});
export const total=(p:Plan)=>p.segments.reduce((n,s)=>n+s.duration,0);
export const offsets=(p:Plan)=>{let n=0;return p.segments.map(s=>{const start=n;n+=s.duration;return {s,start,end:n}})};
export const atFrame=(p:Plan,f:number)=>offsets(p).find(x=>f>=x.start&&f<x.end)||offsets(p).at(-1)!;
export const timecode=(f:number)=>`${Math.floor(f/1800).toString().padStart(2,'0')}:${Math.floor(f/30)%60<10?'0':''}${Math.floor(f/30)%60}:${Math.floor(f%30).toString().padStart(2,'0')}`;
export function captionsFor(words:Word[]):Caption[]{const out:Caption[]=[];let g:Word[]=[];const flush=()=>{if(g.length)out.push({id:uid(),start:g[0].start,end:g.at(-1)!.end,words:g,style:null});g=[]};for(const w of words){if(g.length&&(g.length>=5||g.map(w=>w.text).join(' ').length+w.text.length>35||w.start-g.at(-1)!.end>20||w.end-g[0].start>84))flush();g.push(w);if(/[.!?]$/.test(w.text))flush()}flush();return out}
export function blankPlan(end:number,words:SourceWord[]=[]):Plan {const duration=Math.max(1,Math.round(end*30));return {version:2,fps:30,subtitle_style:style(),segments:[{id:uid(),source_in:0,duration,transform:{legacy_center:false,mode:'fit',x:.5,y:.5,scale:1,b:.7},captions:captionsFor(words.filter(w=>w.start*30<duration).map(w=>({id:`w-${Math.round(w.start*30)}`,start:Math.round(w.start*30),end:Math.min(duration,Math.max(Math.round(w.start*30)+1,Math.round(w.end*30))),text:w.text}))),overlays:[],excluded_word_ids:[]}]}}
export function sliceSegment(s:Segment,a:number,b:number,newId=false):Segment {
 const next=structuredClone(s);next.id=newId?uid():s.id;next.source_in=s.source_in+a;next.duration=b-a;
 next.captions=s.captions.filter(c=>c.end>a&&c.start<b).map(c=>{const words=c.words.filter(w=>w.end>a&&w.start<b).map(w=>({...w,start:Math.max(0,w.start-a),end:Math.min(b-a,w.end-a)}));return {...structuredClone(c),id:newId?uid():c.id,start:Math.max(0,c.start-a),end:Math.min(b-a,c.end-a),words}}).filter(c=>c.words.length);
 next.audio=(s.audio||[]).filter(o=>o.end>a&&o.start<b).map(o=>({...o,id:newId?uid():o.id,source_in:o.source_in+Math.max(0,a-o.start),start:Math.max(0,o.start-a),end:Math.min(b-a,o.end-a)}));
 next.overlays=s.overlays.filter(o=>o.end>a&&o.start<b).map(o=>({...structuredClone(o),id:newId?uid():o.id,start:Math.max(0,o.start-a),end:Math.min(b-a,o.end-a)}));return next;
}
export function splitSegment(p:Plan,frame:number){const x=atFrame(p,frame),cut=frame-x.start;if(cut<1||cut>=x.s.duration)return;const i=p.segments.findIndex(s=>s.id===x.s.id);p.segments.splice(i,1,sliceSegment(x.s,0,cut),sliceSegment(x.s,cut,x.s.duration,true))}
export function trimSegment(p:Plan,id:string,newIn:number,newDuration:number,source:SourceWord[]){const i=p.segments.findIndex(s=>s.id===id),old=p.segments[i];if(!old)return;const delta=newIn-old.source_in;const n=sliceSegment(old,delta,delta+newDuration);n.duration=newDuration;
 const added=source.filter(w=>{const a=Math.round(w.start*30),b=Math.round(w.end*30);return b>newIn&&a<newIn+newDuration&&(b<=old.source_in||a>=old.source_in+old.duration)&&!old.excluded_word_ids.includes(`w-${a}`)}).map(w=>({id:`w-${Math.round(w.start*30)}`,start:Math.max(0,Math.round(w.start*30)-newIn),end:Math.min(newDuration,Math.max(Math.round(w.start*30)+1,Math.round(w.end*30))-newIn),text:w.text})).filter(w=>w.end>w.start);
 n.captions.push(...captionsFor(added));n.captions.sort((a,b)=>a.start-b.start);p.segments[i]=n;
}
export function splitCaption(s:Segment,id:string,frame:number){const i=s.captions.findIndex(c=>c.id===id),c=s.captions[i];if(!c||c.words.length<2)return;const candidates=c.words.slice(1).map(w=>w.start),cut=candidates.reduce((a,b)=>Math.abs(b-frame)<Math.abs(a-frame)?b:a);const left=c.words.filter(w=>w.start<cut).map(w=>({...w,end:Math.min(w.end,cut)})),right=c.words.filter(w=>w.start>=cut);if(!left.length||!right.length)return;s.captions.splice(i,1,{...c,end:cut,words:left},{...structuredClone(c),id:uid(),start:cut,words:right})}
export function resizeCaption(c:Caption,start:number,end:number){const old=c.end-c.start,ratio=(end-start)/old;const words=c.words.map(w=>({...w,start:clamp(Math.round(start+(w.start-c.start)*ratio),start,end-1),end:clamp(Math.round(start+(w.end-c.start)*ratio),start+1,end)}));c.start=start;c.end=end;c.words=words.map(w=>({...w,end:Math.max(w.start+1,w.end)}))}
export function replaceCaptionText(c:Caption,text:string){const tokens=text.trim().split(/\s+/).filter(Boolean);if(!tokens.length){c.words=[];return}if(tokens.length===c.words.length){c.words.forEach((w,i)=>w.text=tokens[i]);return}const span=c.end-c.start;if(tokens.length>span)return;c.words=tokens.map((text,i)=>({id:uid(),start:c.start+Math.floor(span*i/tokens.length),end:c.start+Math.floor(span*(i+1)/tokens.length),text}))}

export function resizeAudio(item:AudioItem,start:number,end:number,assetFrames:number){const delta=start-item.start;const source=item.source_in+delta;const sourceIn=clamp(source,0,Math.max(0,assetFrames-1));const a=start+(sourceIn-source);item.start=a;item.source_in=sourceIn;item.end=Math.max(a+1,Math.min(end,a+assetFrames-sourceIn))}

// End is exclusive: select the last visible frame when the playhead has passed.
export const selectionFrame=(frame:number,start:number,end:number)=>clamp(frame,start,Math.max(start,end-1));
export type TimelineSelection={kind:'video'|'caption'|'overlay'|'audio';id:string;segmentId:string};
export function duplicateItem(p:Plan,sel:TimelineSelection):TimelineSelection|null{
 const s=p.segments.find(s=>s.id===sel.segmentId);if(!s)return null;
 if(sel.kind==='video'){
  const copy=sliceSegment(s,0,s.duration,true);copy.captions.forEach(c=>c.words.forEach(w=>w.id=uid()));
  p.segments.splice(p.segments.indexOf(s)+1,0,copy);return {kind:'video',id:copy.id,segmentId:copy.id};
 }
 if(sel.kind==='caption'){
  const item=s.captions.find(x=>x.id===sel.id);if(!item)return null;const copy=structuredClone(item);copy.id=uid();
  const delta=item.end+(item.end-item.start)<=s.duration?item.end-item.start:0;
  copy.start+=delta;copy.end+=delta;copy.words.forEach(w=>{w.id=uid();w.start+=delta;w.end+=delta});s.captions.push(copy);
  return {...sel,id:copy.id};
 }
 if(sel.kind==='audio'){
  const item=s.audio?.find(x=>x.id===sel.id);if(!item)return null;const copy={...item,id:uid()};
  if(item.end+item.end-item.start<=s.duration){copy.start=item.end;copy.end=copy.start+item.end-item.start}s.audio!.push(copy);return {...sel,id:copy.id};
 }
 const item=s.overlays.find(x=>x.id===sel.id);if(!item)return null;const copy=structuredClone(item);copy.id=uid();copy.layer=Math.min(100,Math.max(0,...s.overlays.map(o=>o.layer))+1);s.overlays.push(copy);return {...sel,id:copy.id};
}
