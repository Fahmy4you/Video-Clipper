const fs=require('fs'),path=require('path'),Module=require('module'),assert=require('node:assert/strict'),cp=require('child_process');
const root=path.resolve(__dirname,'..'),ts=require('../apps/web/node_modules/typescript'),filename=path.join(root,'apps/web/src/subtitlePresentation.ts'),m=new Module(filename,module);
m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const c={start:0,end:30,words:[{start:2,end:12,text:'emas'},{start:17,end:29,text:'naik'}]},cases=[];
for(const mode of ['sentence','word'])for(const animation of ['none','soft_zoom'])for(let frame=0;frame<30;frame++)cases.push([c,{subtitle_mode:mode,subtitle_animation:animation},frame]);
const expected=JSON.parse(cp.execFileSync(path.join(root,'.venv/bin/python'),['-c','import json,sys;from app.subtitle_presentation import presentation;print(json.dumps([presentation(*x) for x in json.load(sys.stdin)]))'],{cwd:root,env:{...process.env,PYTHONPATH:'backend'},input:JSON.stringify(cases),encoding:'utf8'}));
cases.forEach((x,i)=>{const result=m.exports.subtitlePresentation(...x);assert.deepEqual(result.words,expected[i][0]);assert.ok(Math.abs(result.scale-expected[i][1])<1e-10)});console.log('PASS: 120 preview/export frame visibility and animation comparisons');
