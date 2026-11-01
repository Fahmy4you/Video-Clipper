const fs=require('fs'),path=require('path'),Module=require('module'),assert=require('node:assert/strict');
const ts=require('../apps/web/node_modules/typescript'),f=path.resolve(__dirname,'../apps/web/src/sourceRanges.ts'),m=new Module(f,module);m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,f);
const {sourceRanges,rangeLabel,exclusionPrompt}=m.exports,plan=(...ranges)=>({segments:ranges.map(([start,end])=>({source_in:start,duration:end-start}))});
assert.deepEqual(sourceRanges(plan([300,600],[0,150],[150,300],[300,450])),[{start:0,end:600}]);
assert.deepEqual(sourceRanges(plan([300,600],[0,150],[300,600])),[{start:0,end:150},{start:300,end:600}]);
assert.equal(rangeLabel({start:30*789+1,end:30*834-1}),'13:09–13:54');
assert.equal(rangeLabel({start:30*3601,end:30*3662}),'01:00:01–01:01:02');
assert.equal(exclusionPrompt(plan([23700,24150],[24330,25020])),'Jangan ambil bagian 13:10–13:25 dan 13:31–13:54 dari video sumber.');
const p=plan([0,90]);p.segments[0].broll=[{source_in:9000,start:0,end:60}];assert.deepEqual(sourceRanges(p),[{start:0,end:90}]);console.log('PASS: source ranges merge, deletion gaps, reorder, duplicate, rounding, long videos and B-roll independence');
