import {create} from 'zustand';
import type {Clip} from './editorModel';
const key=(id:string)=>'vc-editor-v2:'+id;
function persist(c:Clip){try{localStorage.setItem(key(c.id),JSON.stringify(c))}catch{/* autosave to server remains available */}}
type State={draft:Clip|null;dirty:boolean;conflict:boolean;past:Clip[];future:Clip[];transaction:Clip|null;load:(c:Clip,discard?:boolean)=>void;edit:(fn:(c:Clip)=>void)=>void;begin:()=>void;commit:()=>void;undo:()=>void;redo:()=>void;saved:(snapshot:Clip,result:Clip)=>void;setConflict:()=>void};
export const useVisual=create<State>((set,get)=>({draft:null,dirty:false,conflict:false,past:[],future:[],transaction:null,
 load:(server,discard=false)=>{let draft=server,dirty=false,conflict=false;if(discard)localStorage.removeItem(key(server.id));else try{const raw=localStorage.getItem(key(server.id));if(raw){const cached=JSON.parse(raw) as Clip;if(cached.plan.version===2){draft=cached;dirty=true;conflict=cached.revision!==server.revision}}}catch{}set({draft:structuredClone(draft),dirty,conflict,past:[],future:[],transaction:null})},
 edit:fn=>set(s=>{if(!s.draft)return {};const next=structuredClone(s.draft);fn(next);persist(next);return {draft:next,dirty:true,past:s.transaction?s.past:[...s.past.slice(-99),s.draft],future:[]}}),
 begin:()=>set(s=>({transaction:s.draft?structuredClone(s.draft):null})),
 commit:()=>set(s=>({past:s.transaction&&JSON.stringify(s.transaction.plan)!==JSON.stringify(s.draft?.plan)?[...s.past.slice(-99),s.transaction]:s.past,transaction:null})),
 undo:()=>{if(get().transaction)return;set(s=>{if(!s.past.length||!s.draft)return {};const c={...structuredClone(s.past.at(-1)!),revision:s.draft.revision};persist(c);return {draft:c,dirty:true,past:s.past.slice(0,-1),future:[s.draft,...s.future]}})},
 redo:()=>set(s=>{if(!s.future.length||!s.draft)return {};const c={...structuredClone(s.future[0]),revision:s.draft.revision};persist(c);return {draft:c,dirty:true,past:[...s.past,s.draft],future:s.future.slice(1)}}),
 saved:(snapshot,result)=>set(s=>{if(s.draft?.id!==result.id)return {};const unchanged=JSON.stringify(s.draft.plan)===JSON.stringify(snapshot.plan)&&s.draft.title===snapshot.title;const draft={...s.draft,revision:result.revision};if(unchanged)localStorage.removeItem(key(draft.id));else persist(draft);return {draft,dirty:!unchanged,conflict:false}}),setConflict:()=>set({conflict:true})
}));
