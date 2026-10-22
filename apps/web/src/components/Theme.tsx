import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {Monitor,Sun,Moon} from 'lucide-react';
type Mode='system'|'light'|'dark';
const ThemeContext=createContext<{mode:Mode;setMode:(mode:Mode)=>void}>({mode:'system',setMode:()=>{}});
export function ThemeProvider({children}:{children:ReactNode}){
 const [mode,setMode]=useState<Mode>(()=>{try{const saved=localStorage.getItem('vc-theme');return saved==='light'||saved==='dark'?saved:'system'}catch{return 'system'}});
 useEffect(()=>{const query=matchMedia('(prefers-color-scheme: dark)');const apply=()=>{const theme=mode==='system'?(query.matches?'dark':'light'):mode;document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme;document.querySelector('meta[name="theme-color"]')?.setAttribute('content',theme==='dark'?'#030712':'#f3f4f6');try{localStorage.setItem('vc-theme',mode)}catch{}};apply();query.addEventListener('change',apply);return()=>query.removeEventListener('change',apply)},[mode]);
 return <ThemeContext.Provider value={{mode,setMode}}>{children}</ThemeContext.Provider>;
}
export function ThemeSelect(){const {mode,setMode}=useContext(ThemeContext);const Icon=mode==='light'?Sun:mode==='dark'?Moon:Monitor;return <label className="theme-select"><Icon size={16} aria-hidden="true"/><select aria-label="Tema tampilan" value={mode} onChange={e=>setMode(e.target.value as Mode)}><option value="system">Sistem</option><option value="light">Terang</option><option value="dark">Gelap</option></select></label>}

