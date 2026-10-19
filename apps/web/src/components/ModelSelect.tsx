import {useEffect,useId,useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {api,type ModelOption} from '../api';
import {Button} from './ui/button';

export function ModelSelect({value,onChange,disabled=false}:{value:string;onChange:(value:string)=>void;disabled?:boolean}){
 const id=useId();const [models,setModels]=useState<ModelOption[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
 async function fetchModels(refresh=false){setLoading(true);setError('');try{setModels(await api<ModelOption[]>('/models'+(refresh?'?refresh=true':'')))}catch(e){setModels([]);setError((e as Error).message)}finally{setLoading(false)}}
 useEffect(()=>{void fetchModels()},[]);
 const listed=models.some(m=>m.id===value);
 return <div className="model-picker"><div className="model-picker-heading"><label htmlFor={id}>Model Gemini</label><Button type="button" variant="ghost" aria-label="Muat ulang model" disabled={loading||disabled} onClick={()=>fetchModels(true)}><RefreshCw size={14} className={loading?'spin':''}/></Button></div><select id={id} value={value} onChange={e=>onChange(e.target.value)} disabled={loading||disabled||!!error||!models.length} required aria-describedby={id+'-hint'}><option value="" disabled>{loading?'Memeriksa akses model…':error?'Daftar model belum tersedia':!models.length?'Tidak ada model teks tersedia':'Pilih model untuk proyek ini'}</option>{value&&!listed&&<option value={value} disabled>{value} · {loading?'memeriksa…':'tidak tersedia'}</option>}{models.map(model=><option value={model.id} key={model.id}>{model.name} · {model.id}</option>)}</select><p id={id+'-hint'} className={error?'model-error':'model-hint'} role={error?'alert':undefined}>{error||'Hanya model yang lolos uji JSON dengan API key ini. Pemeriksaan awal dapat memerlukan waktu; hasil disimpan sementara.'}</p></div>
}
