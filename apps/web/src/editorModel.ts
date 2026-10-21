export type Fade={in_frames:number;out_frames:number;span:number;offset:number};
export type Transition={kind:'black'|'crossfade'|'none';frames:number};
export type Ratio='9:16'|'16:9'|'1:1'|'4:5'|'4:3';
export const formats:{id:Ratio;width:number;height:number;label:string;hint:string}[]=[{id:'9:16',width:1080,height:1920,label:'Vertikal',hint:'TikTok · Shorts · Reels · Story'},{id:'16:9',width:1920,height:1080,label:'Horizontal',hint:'YouTube · TV'},{id:'1:1',width:1080,height:1080,label:'Persegi',hint:'Instagram · Facebook'},{id:'4:5',width:1080,height:1350,label:'Portrait',hint:'Feed Instagram'},{id:'4:3',width:1440,height:1080,label:'Klasik',hint:'Format televisi klasik'}];
export type Style={x:number;y:number;width:number;height:number;rotation:number;opacity:number;font:'DejaVu Sans'|'Liberation Sans'|'Poppins';size:number;color:string;highlight:string;outline:number;align:'left'|'center'|'right';karaoke:boolean};
export type Word={id:string;start:number;end:number;text:string};
export type Caption={id:string;start:number;end:number;words:Word[];style:Style|null};
export type Overlay={id:string;kind:'text'|'image';start:number;end:number;text:string;asset_id:string|null;layer:number;style:Style};
export type AudioItem={id:string;asset_id:string;start:number;end:number;source_in:number;volume:number;fade?:Fade};
export type AudioAsset={id:string;name:string;duration:number;frames:number;url:string;waveform:number[];waveform_interval:number;origin:string};
export type Segment={id:string;source_in:number;duration:number;transform:{legacy_center?:boolean;mode:'fit'|'fill'|'split';x:number;y:number;scale:number;b:number};captions:Caption[];overlays:Overlay[];excluded_word_ids:string[];audio?:AudioItem[];broll?:Broll[]};
export type Plan={source_fade?:Fade;source_volume?:number;version:2;fps:30;segments:Segment[];subtitle_style:Style};
export type Clip={id:string;project_id:string;title:string;reason:string;revision:number;fulfills_prompt:boolean;plan:Plan};
export type Project={mix_hashtags?:string[];visual_mode?:'podcast'|'mix';id:string;url:string;title:string;duration:number;status:string;created_at:string;gemini_model:string|null;aspect_ratio:Ratio;highlight_count:number;additional_prompt:string;analysis_report:{mix_message?:string;mix_status?:string;requested?:number;generated?:number;unmet_requests?:string[]}};
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
 next.audio=(s.audio||[]).filter(o=>o.end>a&&o.start<b).map(o=>({...o,id:newId?uid():o.id,fade:{...fadeOf(o),offset:fadeOf(o).offset+Math.max(0,a-o.start)},source_in:o.source_in+Math.max(0,a-o.start),start:Math.max(0,o.start-a),end:Math.min(b-a,o.end-a)}));
 next.broll=(s.broll||[]).filter(o=>o.end>a&&o.start<b).map(o=>({...structuredClone(o),id:newId?uid():o.id,source_in:o.source_in+Math.max(0,a-o.start),start:Math.max(0,o.start-a),end:Math.min(b-a,o.end-a),transition_in:o.start<a?{kind:'none',frames:0}:o.transition_in,transition_out:o.end>b?{kind:'none',frames:0}:o.transition_out}));
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

export function resizeAudio(item:AudioItem,start:number,end:number,assetFrames:number){const delta=start-item.start;const source=item.source_in+delta;const sourceIn=clamp(source,0,Math.max(0,assetFrames-1));const a=start+(sourceIn-source);if(item.fade?.span)item.fade={...item.fade,offset:Math.max(0,item.fade.offset+a-item.start)};item.start=a;item.source_in=sourceIn;item.end=Math.max(a+1,Math.min(end,a+assetFrames-sourceIn))}

// End is exclusive: select the last visible frame when the playhead has passed.
export const selectionFrame=(frame:number,start:number,end:number)=>clamp(frame,start,Math.max(start,end-1));
export type TimelineSelection={kind:'video'|'caption'|'overlay'|'audio'|'broll';id:string;segmentId:string};
export function duplicateItem(p:Plan,sel:TimelineSelection):TimelineSelection|null{
 const s=p.segments.find(s=>s.id===sel.segmentId);if(!s||sel.kind==='broll')return null;
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

export type Broll={id:string;asset_id:string;start:number;end:number;source_in:number;reason:string;transform:Segment['transform'];transition_in:Transition;transition_out:Transition};
export type VideoAsset={id:string;title:string;hashtags:string[];hashtag_ids:string[];explain:string;scenes:{start:number;end:number;explain:string}[];duration:number;frames:number;width:number;height:number;status:string;error:string|null;archived:boolean;revision:number;proxy_url:string;thumbnail_url:string;thumbnail_base:string};
export const emptyFade=():Fade=>({in_frames:0,out_frames:0,span:0,offset:0});
export const fadeOf=(a:AudioItem):Fade=>({...emptyFade(),...a.fade,span:a.fade?.span||a.end-a.start});
export function fadeGain(f:Fade|undefined,frame:number,length:number){if(!f)return 1;const span=f.span||length,x=frame+f.offset;return clamp(Math.min(1,f.in_frames?x/Math.min(f.in_frames,span):1,f.out_frames?(span-x)/Math.min(f.out_frames,span):1),0,1)}
export function brollLimits(item:Broll,items:Broll[],duration:number,frames:number){const sorted=[...items].sort((a,b)=>a.start-b.start),i=sorted.findIndex(b=>b.id===item.id),prev=i?sorted[i-1].end:0,next=i+1<sorted.length?sorted[i+1].start:duration;return [true,false].map(enter=>{const edge=enter?item.transition_in:item.transition_out,half=Math.floor(Math.min(edge.frames/2,(item.end-item.start)/2,(enter?item.start-prev:next-item.end)/2));let kind=edge.kind;if(kind==='crossfade'&&(enter?item.source_in<half:item.source_in+item.end-item.start+half>frames))kind='black';return {kind,half:kind==='none'?0:half,fallback:kind!==edge.kind}})}
export function brollWeights(item:Broll,items:Broll[],duration:number,frames:number,f:number){const [a,b]=brollLimits(item,items,duration,frames),up=a.half?(a.kind==='crossfade'?clamp((f-item.start+a.half)/(2*a.half),0,1):clamp((f-item.start)/a.half,0,1)):+(f>=item.start),down=b.half?(b.kind==='crossfade'?clamp((item.end+b.half-f)/(2*b.half),0,1):clamp((item.end-f)/b.half,0,1)):+(f<item.end);const before=a.kind==='crossfade'?1-up:a.half?clamp((item.start-f)/a.half,0,1):+(f<item.start),after=b.kind==='crossfade'?1-down:b.half?clamp((f-item.end)/b.half,0,1):+(f>=item.end);return {base:Math.max(before,after),clip:Math.min(up,down)}}
export const brollFits=(s:Segment,a:number,b:number,except?:string)=>a>=0&&b>a&&b<=s.duration&&!(s.broll||[]).some(x=>x.id!==except&&a<x.end&&b>x.start);

export const globalBroll=(p:Plan)=>offsets(p).flatMap(r=>(r.s.broll||[]).map(b=>({...b,start:b.start+r.start,end:b.end+r.start,segmentId:r.s.id})));

export function placeBroll(p:Plan,item:Broll,start:number,end:number,replaceId?:string):TimelineSelection|null{
 if(start<0||end<=start||end>total(p)||globalBroll(p).some(b=>b.id!==replaceId&&start<b.end&&end>b.start))return null;
 if(replaceId)for(const s of p.segments)s.broll=(s.broll||[]).filter(b=>b.id!==replaceId);
 let selected:TimelineSelection|null=null;
 for(const r of offsets(p)){const a=Math.max(start,r.start),b=Math.min(end,r.end);if(b<=a)continue;const id:string=selected?uid():item.id;(r.s.broll??=[]).push({...structuredClone(item),id,start:a-r.start,end:b-r.start,source_in:item.source_in+a-start,transition_in:a===start?item.transition_in:{kind:'none',frames:0},transition_out:b===end?item.transition_out:{kind:'none',frames:0}});selected??={kind:'broll',segmentId:r.s.id,id}}
 return selected;
}
