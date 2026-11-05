type Decoder={node:HTMLVideoElement;url:string;presented:number;lastFrame:number;lastSeek:number;waitingSince:number;callback:number;dispose:()=>void};
export type MediaNeed={id:string;assetId:string;url:string;proxy:string;time:number;active:boolean};
export class PreviewMedia {
 records=new Map<string,{current:Decoder;old?:Decoder}>();failed=new Set<string>();container:HTMLElement;warning:(s:string)=>void;
 constructor(container:HTMLElement,warning:(s:string)=>void){this.container=container;this.warning=warning}
 create(url:string){const node=document.createElement('video');node.muted=true;node.playsInline=true;node.preload='auto';node.className='decode-video broll-decode';node.src=url;this.container.appendChild(node);const d:Decoder={node,url,presented:0,lastFrame:performance.now(),lastSeek:-Infinity,waitingSince:0,callback:0,dispose:()=>{node.pause();if(d.callback)node.cancelVideoFrameCallback(d.callback);node.removeAttribute('src');node.load();node.remove()}};const frame=(_now:number,metadata?:VideoFrameCallbackMetadata)=>{d.presented=metadata?.mediaTime??node.currentTime;d.lastFrame=performance.now();if(typeof node.requestVideoFrameCallback==='function')d.callback=node.requestVideoFrameCallback(frame)};node.addEventListener('seeked',()=>{d.presented=node.currentTime;d.lastFrame=performance.now()});node.addEventListener('loadeddata',()=>{d.presented=node.currentTime;d.lastFrame=performance.now()});if(typeof node.requestVideoFrameCallback==='function')d.callback=node.requestVideoFrameCallback(frame);return d}
 fallback(n:MediaNeed){if(this.failed.has(n.assetId))return;this.failed.add(n.assetId);this.warning('Sumber asli sisipan tidak dapat diputar stabil. Aset ini memakai Proxy selama sesi editor.');}
 update(needs:MediaNeed[],playing:boolean){const ids=new Set(needs.map(n=>n.id));for(const [id,r]of this.records)if(!ids.has(id)){r.current.dispose();r.old?.dispose();this.records.delete(id)}let ready=true;const chosen=new Map<string,HTMLVideoElement>();
 for(const n of needs){let url=this.failed.has(n.assetId)?n.proxy:n.url,r=this.records.get(n.id);if(!r){r={current:this.create(url)};this.records.set(n.id,r)}else if(r.current.url!==url){r.old?.dispose();r.old=r.current;r.current=this.create(url)}const d=r.current,v=d.node,now=performance.now();
  if(typeof v.requestVideoFrameCallback!=='function'&&v.readyState>=2&&!v.seeking){if(d.presented!==v.currentTime)d.lastFrame=now;d.presented=v.currentTime}
  if(v.readyState&&!v.seeking&&Math.abs(v.currentTime-n.time)>(playing?.25:.018)&&now-d.lastSeek>(playing?500:40)){v.currentTime=n.time;d.lastSeek=now;d.presented=NaN}
  const decoded=v.readyState>=2&&v.videoWidth>0&&!v.seeking&&Number.isFinite(d.presented)&&Math.abs(d.presented-n.time)<(playing?.3:.05);
  if(!decoded){d.waitingSince||=now;if(n.url!==n.proxy&&(v.error||v.readyState>=1&&!v.videoWidth||now-d.waitingSince>5000))this.fallback(n)}else d.waitingSince=0;
  if(playing&&n.active&&!v.paused&&now-d.lastFrame>5000&&n.url!==n.proxy)this.fallback(n);
  if(decoded){chosen.set(n.id,v);r.old?.dispose();r.old=undefined}else{if(n.active)ready=false;const old=r.old?.node;if(old&&old.readyState>=2&&!old.seeking)chosen.set(n.id,old)}
 }
 return {ready,chosen};}
 playback(needs:MediaNeed[],run:boolean){for(const n of needs){const r=this.records.get(n.id);for(const d of [r?.current,r?.old]){if(!d)continue;if(run&&n.active&&d===r?.current){if(d.node.paused)void d.node.play().catch(()=>{})}else d.node.pause()}}}
 dispose(){for(const r of this.records.values()){r.current.dispose();r.old?.dispose()}this.records.clear()}
}
