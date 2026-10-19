import {create} from 'zustand';
import type {Clip} from './api';
type State={draft:Clip|null;dirty:boolean;past:Clip[];future:Clip[];load:(clip:Clip)=>void;edit:(fn:(c:Clip)=>void)=>void;undo:()=>void;redo:()=>void};
export const useEditor=create<State>((set)=>({draft:null,dirty:false,past:[],future:[],load:clip=>set({draft:structuredClone(clip),dirty:false,past:[],future:[]}),edit:fn=>set(s=>{if(!s.draft)return {};const next=structuredClone(s.draft);fn(next);return {draft:next,dirty:true,past:[...s.past.slice(-29),s.draft],future:[]}}),undo:()=>set(s=>s.past.length?{draft:s.past.at(-1)!,past:s.past.slice(0,-1),future:[s.draft!,...s.future],dirty:true}:{}),redo:()=>set(s=>s.future.length?{draft:s.future[0],past:[...s.past,s.draft!],future:s.future.slice(1),dirty:true}:{})}));
