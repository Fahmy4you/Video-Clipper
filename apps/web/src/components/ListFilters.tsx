import {useId,useRef,useState,type ReactNode} from 'react';
import {SlidersHorizontal,RotateCcw,X} from 'lucide-react';
import './list-filters.css';

export function FilterDock({children,summary,active,onReset}:{children:ReactNode;summary:string;active:boolean;onReset:()=>void}){
 const [open,setOpen]=useState(false),id=useId(),trigger=useRef<HTMLButtonElement>(null);
 function close(){setOpen(false);trigger.current?.focus()}
 return <div className="list-filters" onKeyDown={e=>{if(open&&e.key==='Escape'){e.preventDefault();close()}}}>
  <div className="list-filter-toolbar"><button ref={trigger} type="button" className={'button secondary filter-toggle '+(active?'is-active':'')} aria-expanded={open} aria-controls={id} onClick={()=>setOpen(!open)}><SlidersHorizontal size={17}/>Filter & urutkan{active&&<span className="filter-active-dot" aria-label="Pengaturan aktif"/>}</button><span className="list-filter-summary">{summary}</span>{active&&<button type="button" className="filter-reset" onClick={onReset}><RotateCcw size={14}/>Reset</button>}</div>
  {open&&<section id={id} className="list-filter-dock" aria-label="Filter dan urutan data" onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();close()}}}>
   <header><div><h2>Filter & urutkan</h2><p>Daftar langsung diperbarui saat pilihan berubah.</p></div><button type="button" className="icon-button" title="Tutup filter" aria-label="Tutup filter" onClick={close}><X size={17}/></button></header><div className="list-filter-fields">{children}</div>
  </section>}
 </div>
}
export function SortSelect({value,onChange,options}:{value:string;onChange:(value:string)=>void;options:{value:string;label:string}[]}){return <label>Urutkan berdasarkan<select aria-label="Urutkan berdasarkan" value={value} onChange={e=>onChange(e.target.value)}>{options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></label>}
export function DateRange({label,from,to,onChange}:{label:string;from:string;to:string;onChange:(from:string,to:string)=>void}){
 const invalid=!!from&&!!to&&from>to;
 return <fieldset className="filter-date-range"><legend>{label}</legend><div><label>Dari<input aria-label={label+' dari'} type="date" value={from} max={to||undefined} aria-invalid={invalid||undefined} onChange={e=>onChange(e.target.value,to)}/></label><label>Sampai<input aria-label={label+' sampai'} type="date" value={to} min={from||undefined} aria-invalid={invalid||undefined} onChange={e=>onChange(from,e.target.value)}/></label></div>{invalid&&<p role="alert" className="filter-error">Tanggal akhir harus sama atau setelah tanggal awal.</p>}</fieldset>
}
