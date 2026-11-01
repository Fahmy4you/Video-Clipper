import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[react(),tailwindcss()],server:{fs:{deny:['**/.env','**/.env.*','**/*.{crt,pem}','**/.git/**','**/apikey.json','**/apikey.json.tmp','**/apikey.json.lock']},port:5173,strictPort:true,proxy:{'/api':'http://127.0.0.1:8000'}}});
