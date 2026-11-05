export type PreviewStatus = {phase:'preparing'|'seeking'|'waiting'|'ready'|'failed';completed:number;total:number;error?:string};
export type MediaNeed = {id:string;assetId:string;url:string;proxy:string;time:number;active:boolean};
export type PreviewFrame = HTMLVideoElement | HTMLCanvasElement;
type Decoder = {node:HTMLVideoElement;url:string;presented:number;lastFrame:number;lastSeek:number;waitingSince:number;used:number;callback:number;dispose:()=>void};
const CACHE_LIMIT = 64 * 1024 * 1024;
const frameKey = (n:MediaNeed,url:string) => url+'@'+Math.round(n.time*30);

export class PreviewMedia {
 records = new Map<string,Decoder>();
 failed = new Set<string>();
 prepared = new Set<string>();
 cache = new Map<string,HTMLCanvasElement>();
 cacheBytes = 0;
 error = '';
 constructor(private container:HTMLElement,private warning:(s:string)=>void) {}
 private url(n:MediaNeed) { return this.failed.has(n.assetId)?n.proxy:n.url; }
 private create(url:string):Decoder {
  const node=document.createElement('video');
  node.muted=true;node.playsInline=true;node.preload='auto';node.className='decode-video broll-decode';
  const d:Decoder={node,url,presented:NaN,lastFrame:performance.now(),lastSeek:-Infinity,waitingSince:0,used:0,callback:0,dispose:()=>{node.pause();if(d.callback)node.cancelVideoFrameCallback(d.callback);node.removeAttribute('src');node.load();node.remove();}};
  const frame=(_now:number,m?:VideoFrameCallbackMetadata)=>{
   d.presented=m?.mediaTime??node.currentTime;d.lastFrame=performance.now();
   if(typeof node.requestVideoFrameCallback==='function')d.callback=node.requestVideoFrameCallback(frame);
  };
  const ready=()=>{d.presented=node.currentTime;d.lastFrame=performance.now();};
  node.addEventListener('loadeddata',ready);node.addEventListener('seeked',ready);
  if(typeof node.requestVideoFrameCallback==='function')d.callback=node.requestVideoFrameCallback(frame);
  node.src=url;this.container.appendChild(node);
  return d;
 }
 private remember(n:MediaNeed,d:Decoder) {
  const key=frameKey(n,d.url);
  if(this.cache.has(key)||!d.node.videoWidth)return;
  const size=d.node.videoWidth*d.node.videoHeight*4;
  if(size>CACHE_LIMIT)return;
  while(this.cacheBytes+size>CACHE_LIMIT&&this.cache.size){
   const [k,c]=this.cache.entries().next().value!;
   this.cache.delete(k);this.cacheBytes-=c.width*c.height*4;c.width=c.height=0;
  }
  const c=document.createElement('canvas');c.width=d.node.videoWidth;c.height=d.node.videoHeight;
  c.getContext('2d')!.drawImage(d.node,0,0);this.cache.set(key,c);this.cacheBytes+=size;
 }
 private fallback(n:MediaNeed) {
  if(this.failed.has(n.assetId))return;
  this.failed.add(n.assetId);
  this.warning('Sumber asli sisipan belum dapat diputar stabil. Aset ini memakai rendering ringan selama sesi editor.');
 }
 update(needs:MediaNeed[],playing:boolean) {
  this.error='';
  // Active frames take priority over prefetch. Keep at most four visual decoders.
  const ordered=[...needs].sort((a,b)=>Number(b.active)-Number(a.active));
  const requests=ordered.filter((n,i)=>ordered.findIndex(x=>x.id===n.id)===i).slice(0,4);
  const wanted=new Set(requests.map(n=>n.id));
  const chosen=new Map<string,PreviewFrame>();
  let ready=true;
  for(const n of requests) {
   const url=this.url(n);let d=this.records.get(n.id);
   if(d&&d.url!==url){d.dispose();this.records.delete(n.id);d=undefined;}
   if(!d){
    if(this.records.size>=4){
     const victim=[...this.records].filter(([id])=>!wanted.has(id)).sort((a,b)=>a[1].used-b[1].used)[0];
     if(victim){victim[1].dispose();this.records.delete(victim[0]);}
    }
    if(this.records.size>=4){if(n.active)ready=false;continue;}
    d=this.create(url);this.records.set(n.id,d);
   }
   const v=d.node,now=performance.now();d.used=now;
   if(typeof v.requestVideoFrameCallback!=='function'&&v.readyState>=2&&!v.seeking){d.presented=v.currentTime;d.lastFrame=now;}
   // Playback tolerance follows user intent, including while internally paused.
   const tolerance=playing && n.active ? .30 : .05;
   if(v.readyState&&!v.seeking&&Math.abs(v.currentTime-n.time)>(playing && n.active ? .25 : .018)&&now-d.lastSeek>(playing&&n.active?500:40)){
    v.currentTime=Math.max(0,Math.min(n.time,Number.isFinite(v.duration)?Math.max(0,v.duration-.034):n.time));
    d.lastSeek=now;d.presented=NaN;
   }
   const decoded=v.readyState>=2&&v.videoWidth>0&&!v.seeking&&Number.isFinite(d.presented)&&Math.abs(d.presented-n.time)<tolerance;
   if(decoded){
    chosen.set(n.id,v);d.waitingSince=0;
    if(!playing||!n.active)this.remember(n,d);
   }else{
    d.waitingSince||=now;
    if(url!==n.proxy&&(v.error||now-d.waitingSince>5000))this.fallback(n);
    else if(v.error||now-d.waitingSince>12000)this.error='Media preview tidak dapat disiapkan. Periksa file sumber lalu coba lagi.';
    const cached=this.cache.get(frameKey(n,url));
    if(!playing&&cached)chosen.set(n.id,cached);
    else if(n.active)ready=false;
   }
  }
  return {ready,chosen};
 }
 playback(needs:MediaNeed[],run:boolean) {
  const active=new Set(needs.filter(n=>n.active).map(n=>n.id));
  for(const [id,d]of this.records){
   if(run&&active.has(id)){if(d.node.paused)void d.node.play().catch(()=>{});}
   else if(!d.node.paused)d.node.pause();
  }
 }
 async prepare(needs:MediaNeed[],cancelled:()=>boolean,progress:(completed:number,total:number)=>void) {
  let done=0;progress(0,needs.length);
  for(const n of needs){
   if(cancelled())return;
   let key=frameKey(n,this.url(n));
   if(!this.prepared.has(key)){
    const start=performance.now();
    while(!cancelled()){
     const state=this.update([{...n,active:true}],false);
     if(state.ready){this.prepared.add(frameKey(n,this.url(n)));break;}
     if(this.error||performance.now()-start>16000)throw new Error(this.error||'Waktu persiapan media habis. Coba lagi.');
     await new Promise(resolve=>setTimeout(resolve,25));
    }
   }
   if(cancelled())return;
   progress(++done,needs.length);
  }
 }
 async prepareExtra(url:string,kind:'image'|'audio',time:number,cancelled:()=>boolean) {
  const key=kind+':'+url+'@'+time;
  if(this.prepared.has(key)||cancelled())return;
  if(!url)throw new Error('Aset gambar atau audio tidak ditemukan.');
  if(kind==='image'){
   const image=new Image();image.src=url;
   let timer:ReturnType<typeof setTimeout>|undefined;
   try{await Promise.race([image.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Gambar belum dapat dimuat.')),12000)})]);}
   finally{clearTimeout(timer);}
  }else{
   const node=new Audio();node.preload='auto';node.src=url;
   try{
    const start=performance.now();
    while(!cancelled()){
     if(node.error||performance.now()-start>12000)throw new Error('Audio tambahan belum dapat disiapkan.');
     if(node.readyState&&!node.seeking&&Math.abs(node.currentTime-time)>.05)node.currentTime=time;
     if(node.readyState>=2&&!node.seeking&&Math.abs(node.currentTime-time)<=.05)break;
     await new Promise(resolve=>setTimeout(resolve,25));
    }
   }finally{node.pause();node.removeAttribute('src');node.load();}
  }
  if(!cancelled())this.prepared.add(key);
 }
 dispose() {
  for(const d of this.records.values())d.dispose();
  this.records.clear();for(const c of this.cache.values())c.width=c.height=0;
  this.cache.clear();this.cacheBytes=0;this.prepared.clear();
 }
}
