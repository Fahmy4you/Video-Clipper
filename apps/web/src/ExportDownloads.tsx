import {useEffect,useState} from 'react';
import {Download,X} from 'lucide-react';
import {api,type Job} from './api';
const STORAGE='vc-export-watch';
type Watch={id:string;projectId:string;notified?:boolean};
let fallback:Watch[]=[];
function read():Watch[]{try{return JSON.parse(localStorage.getItem(STORAGE)||'[]')}catch{return fallback}}
function write(records:Watch[]){fallback=records;try{localStorage.setItem(STORAGE,JSON.stringify(records))}catch{}}
export function watchExport(job:Job){
 const records=read();if(!records.some(r=>r.id===job.id))records.push({id:job.id,projectId:job.project_id!});
 write(records.slice(-30));window.dispatchEvent(new CustomEvent('vc-export-watch',{detail:job.id}));
}
export function ExportDownloads(){
 const [finished,setFinished]=useState<Job[]>([]),[attempted,setAttempted]=useState(new Set<string>());
 useEffect(()=>{
  let live=true,busy=false;
  const seenPending=new Set<string>();
  const refresh=async()=>{
   if(busy)return;busy=true;
   try{
    for(const item of read().filter(r=>!r.notified)){
     let j:Job;try{j=await api<Job>('/jobs/'+item.id)}catch{continue}
     if(!live)return;
     if(['queued','running','waiting_service','waiting_quota','cancelling'].includes(j.status)){seenPending.add(j.id);continue}
     const records=read();const r=records.find(r=>r.id===j.id);if(!r||r.notified)continue;r.notified=true;
     write(records);
     if(j.status==='succeeded'){
      setFinished(old=>[...old.filter(x=>x.id!==j.id),j]);
      if(seenPending.has(j.id)&&j.result.export_mode!=='local'){
       setAttempted(ids=>new Set(ids).add(j.id));
       const a=document.createElement('a');a.href=j.result.download_url||'/api/exports/'+j.id+'/download';a.download='';document.body.appendChild(a);a.click();a.remove();
      }
     }
    }
   }finally{busy=false}
  };
  const added=(event:Event)=>{seenPending.add((event as CustomEvent<string>).detail);void refresh()};
  window.addEventListener('vc-export-watch',added);void refresh();
  const timer=setInterval(refresh,2000);
  return()=>{live=false;clearInterval(timer);window.removeEventListener('vc-export-watch',added)};
 },[]);
 return <div className="export-notifications">{finished.map(j=><div role="status" key={j.id}><span>{j.result.local_path?'Tersimpan di '+j.result.local_path:'Ekspor '+(j.result.resolution||1080)+'p selesai'}</span><a href={j.result.download_url||'/api/exports/'+j.id+'/download'} download onClick={()=>setAttempted(ids=>new Set(ids).add(j.id))}><Download size={14}/>{j.result.local_path?'Unduh salinan':attempted.has(j.id)?'Unduh ulang':'Unduh MP4'}</a><button aria-label="Tutup pemberitahuan ekspor" onClick={()=>setFinished(rows=>rows.filter(r=>r.id!==j.id))}><X size={15}/></button></div>)}</div>
}
