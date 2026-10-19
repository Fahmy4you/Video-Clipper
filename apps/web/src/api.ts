export type {Word,Plan,Project,Clip} from './editorModel';
export {blankPlan} from './editorModel';
export type Job={id:string;project_id:string;clip_id:string|null;kind:string;status:string;stage:string;progress:number;error:string|null;payload:Record<string,unknown>;result:{url?:string;revision?:number};created_at:string};
export type ModelOption={id:string;name:string};
export type Health={database:string;redis:boolean;ffmpeg:boolean;gemini:boolean};
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok){const d=data.detail;throw Object.assign(new Error(typeof d==='string'?d:Array.isArray(d)?d.map((x:{msg:string})=>x.msg).join('; '):'Permintaan gagal.'),{status:r.status})}return data}
export function stamp(t:number){return `${Math.floor(t/60).toString().padStart(2,'0')}:${Math.floor(t%60).toString().padStart(2,'0')}`}
