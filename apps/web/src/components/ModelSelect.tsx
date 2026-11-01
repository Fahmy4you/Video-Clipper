import {useEffect,useId,useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {api,type ModelCatalog} from '../api';
import {Button} from './ui/button';

export const modelStatus:Record<string,string>={catalog:'Tercantum di katalog',used:'Pernah berhasil digunakan',waiting_quota:'Menunggu kuota',waiting_service:'Menunggu layanan',denied:'Akses ditolak / tidak tersedia'};
export function ModelSelect({value,onChange,disabled=false}:{value:string;onChange:(value:string)=>void;disabled?:boolean}){
 const id=useId();const [catalog,setCatalog]=useState<ModelCatalog|null>(null),[error,setError]=useState(''),[requesting,setRequesting]=useState(false),[version,setVersion]=useState(0);
 useEffect(()=>{let live=true;let timer:ReturnType<typeof setTimeout>;async function poll(){try{const result=await api<ModelCatalog>('/model-catalog');if(!live)return;setCatalog(result);setError('');if(result.refreshing)timer=setTimeout(poll,2000)}catch(e){if(live)setError((e as Error).message)}}void poll();return()=>{live=false;clearTimeout(timer)}},[version]);
 async function refresh(){setRequesting(true);setError('');try{const result=await api<ModelCatalog>('/model-catalog/refresh','POST',{});setCatalog(result);setVersion(v=>v+1)}catch(e){setError((e as Error).message)}finally{setRequesting(false)}}
 const models=catalog?.models||[],updating=!!catalog?.refreshing||requesting,loading=!catalog&&!error,selected=models.find(m=>m.id===value),completed=catalog?.connections.filter(c=>!c.refreshing).length||0;
 const failures=catalog?.connections.filter(c=>c.error)||[],fetched=catalog?.connections.map(c=>c.fetched_at).filter((x):x is string=>!!x).sort().at(0);
 return <div className="model-picker"><div className="model-picker-heading"><label htmlFor={id}>Model Gemini</label><Button type="button" variant="ghost" aria-label="Perbarui katalog model" title="Perbarui katalog tanpa mengirim prompt" disabled={updating||disabled} onClick={()=>void refresh()}><RefreshCw size={14} className={updating?'spin':''}/></Button></div>
 <select id={id} value={value} onChange={e=>onChange(e.target.value)} disabled={disabled||!models.length} required aria-describedby={id+'-hint'}><option value="" disabled>{loading||updating&&!models.length?'Memuat katalog model…':!models.length?'Katalog model belum tersedia':'Pilih model untuk proyek ini'}</option>{value&&!selected&&<option value={value} disabled>{value} · tidak tercantum di katalog</option>}{models.map(model=><option value={model.id} key={model.id} disabled={!model.selectable}>{model.name} · {model.id} · {modelStatus[model.status]||model.status}</option>)}</select>
 <p id={id+'-hint'} className={error?'model-error':'model-hint'} role={error?'alert':'status'}>{error||<>{updating?`Memperbarui metadata ${completed}/${catalog?.connections.length||0} koneksi. `:''}{selected?modelStatus[selected.status]+'. ':''}Daftar dibaca tanpa prompt. Akses generate dan kuota diketahui saat pekerjaan dijalankan.{catalog?.stale&&fetched?' Menampilkan cache '+new Date(fetched).toLocaleString('id-ID')+'.':''}{!catalog?.connections.length&&!loading?' Tambahkan koneksi Gemini di Pengaturan.':''}{failures.length>0?' '+failures.length+' koneksi belum dapat diperbarui; periksa Pengaturan.':''}</>}</p>
 </div>
}
