const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');
fs.mkdirSync('storage/qa',{recursive:true});
(async()=>{
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1366,height:900}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://localhost:5173');
await page.getByRole('heading',{name:/Cerita panjang/}).waitFor();
await page.screenshot({path:'storage/qa/dashboard-desktop.png',fullPage:true});
for(const width of [768,390]){
 await page.setViewportSize({width,height:900});
 await page.screenshot({path:`storage/qa/dashboard-${width}.png`,fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error(`Overflow dashboard ${width}`);
}
await page.getByRole('link',{name:'Konfigurasi',exact:true}).click();
await page.getByRole('heading',{name:'Semua dimulai dari sini.'}).waitFor();
await page.screenshot({path:'storage/qa/settings-mobile.png',fullPage:true});
if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Overflow settings');
// Isolated UI fixture: does not create sample data in the application database.
const project={id:'00000000-0000-0000-0000-000000000001',title:'Podcast pengujian editor',gemini_model:'gemini-test',url:'https://www.youtube.com/watch?v=dQw4w9WgXcQ',duration:120,status:'ready',created_at:new Date().toISOString()};
let clip={id:'00000000-0000-0000-0000-000000000002',project_id:project.id,title:'Membangun kebiasaan kecil',reason:'Fixture pengujian, bukan hasil analisis AI.',revision:1,plan:{start:10,end:45,words:[{start:0,end:.5,text:'Mulai'},{start:.5,end:1,text:'dari'},{start:1,end:1.5,text:'sekarang'}],layouts:[{start:0,mode:'fit',a:.3,b:.7}],style:{font:'DejaVu Sans',size:62,color:'#FFFFFF',highlight:'#5EEAD4',outline:3,margin:180}}};
let saves=0,renders=0;
await page.route('**/api/**',async route=>{
 const u=new URL(route.request().url()),path=u.pathname;
 let data;
 if(path==='/api/models')data=[{id:'gemini-test',name:'Test Gemini'}];
 else if(path==='/api/health')data={database:'ready',redis:true,ffmpeg:true,gemini:true,model:'test'};
 else if(path===`/api/projects/${project.id}`)data=project;
 else if(path.endsWith('/clips')&&route.request().method()==='GET')data=[clip];
 else if(path.endsWith('/jobs'))data=[];
 else if(path===`/api/clips/${clip.id}`&&route.request().method()==='PATCH'){clip={...clip,...route.request().postDataJSON(),revision:clip.revision+1};saves++;data=clip;}
 else if(path.endsWith('/preview')){renders++;data={id:'test-job',status:'queued'};}
 else data=[];
 await route.fulfill({json:data});
});
await page.setViewportSize({width:1366,height:900});
await page.goto('http://localhost:5173/projects/'+project.id);
await page.getByRole('textbox',{name:'Judul clip'}).waitFor();
await page.getByRole('textbox',{name:'Judul clip'}).fill('Judul yang diedit');
await page.getByRole('button',{name:'Undo',exact:true}).click();
if(await page.getByRole('textbox',{name:'Judul clip'}).inputValue()!=='Membangun kebiasaan kecil')throw new Error('Undo gagal');
await page.getByRole('button',{name:'Redo',exact:true}).click();
await page.getByRole('button',{name:'Simpan',exact:true}).click();
await page.getByRole('button',{name:'Tersimpan',exact:true}).waitFor();
await page.getByRole('button',{name:'Framing',exact:true}).click();
await page.locator('.layouts select').selectOption('split');
await page.getByRole('button',{name:'Render preview',exact:true}).click();
await page.getByRole('button',{name:'Tersimpan',exact:true}).waitFor();
await page.screenshot({path:'storage/qa/editor-desktop.png',fullPage:true});
for(const width of [768,390]){
 await page.setViewportSize({width,height:900});
 await page.screenshot({path:`storage/qa/editor-${width}.png`,fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error(`Overflow editor ${width}`);
}
if(saves!==2||renders!==1)throw new Error(`Expected 2 saves, 1 preview: ${saves}, ${renders}`);
if(errors.length)throw new Error(errors.join('\n'));
const report={result:'passed',viewports:[1366,768,390],pageErrors:errors,fixtureTests:['edit title','undo','redo','save revision','split layout','save before preview'],saves,renders};
fs.writeFileSync('storage/qa/ui-report.json',JSON.stringify(report,null,2));console.log(report);
await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
