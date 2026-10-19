const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),Module=require('module');
const ts=require('../apps/web/node_modules/typescript');
const filename=path.resolve(__dirname,'../apps/web/src/editorModel.ts'),m=new Module(filename,module);
m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const E=m.exports;
const words=[{start:0,end:1,text:'Pertama'},{start:1,end:2,text:'kedua'},{start:2,end:3,text:'ketiga'},{start:3,end:4,text:'keempat'}];
const p=E.blankPlan(4,words),s=p.segments[0];s.overlays.push({id:'o',kind:'text',start:30,end:90,text:'Tetap terikat',asset_id:null,layer:1,style:E.style()});
E.splitSegment(p,60);assert.equal(p.segments.length,2);assert.equal(E.total(p),120);assert.equal(p.segments[1].source_in,60);assert.equal(p.segments[0].overlays[0].end,60);assert.equal(p.segments[1].overlays[0].start,0);assert.equal(p.segments[1].overlays[0].end,30);
assert.equal(p.segments[1].captions.flatMap(c=>c.words)[0].text,'ketiga');assert.equal(p.segments[1].captions.flatMap(c=>c.words)[0].start,0);
p.segments.reverse();assert.equal(E.atFrame(p,0).s.source_in,60);p.segments.splice(1,1);assert.equal(E.total(p),60);
const q=E.blankPlan(4,words),id=q.segments[0].id;E.trimSegment(q,id,30,60,words);q.segments[0].captions[0].words[0].text='KOREKSI';E.trimSegment(q,id,0,120,words);assert.equal(q.segments[0].captions.flatMap(c=>c.words).filter(w=>w.text==='KOREKSI').length,1);assert.equal(q.segments[0].captions.flatMap(c=>c.words).length,4);
const b=E.blankPlan(4,words);E.splitCaption(b.segments[0],b.segments[0].captions[0].id,25);assert.equal(b.segments[0].captions.length,3);assert.equal(b.segments[0].duration,120);
const c=b.segments[0].captions[0];E.resizeCaption(c,5,35);assert.ok(c.words.every(w=>w.start>=5&&w.end<=35));E.replaceCaptionText(c,'Teks baru');assert.equal(c.words.map(w=>w.text).join(' '),'Teks baru');assert.equal(c.words[1].end,35);
assert.equal(E.timecode(1831),'01:01:01');console.log('PASS: split, linked overlays/subtitles, reorder, ripple delete, trim restore, correction preservation, subtitle split/retime and text editing');

const soundPlan=E.blankPlan(6),soundSeg=soundPlan.segments[0];soundSeg.audio=[{id:'sound',asset_id:'00000000-0000-0000-0000-000000000001',start:15,end:165,source_in:30,volume:.4}];E.splitSegment(soundPlan,90);assert.equal(soundPlan.segments[0].audio[0].end,90);assert.equal(soundPlan.segments[1].audio[0].source_in,105);assert.equal(soundPlan.segments[1].audio[0].start,0);assert.equal(soundPlan.segments[1].audio[0].end,75);const trimmed=E.sliceSegment(soundPlan.segments[1],15,60);assert.equal(trimmed.audio[0].source_in,120);assert.equal(trimmed.audio[0].end,45);E.resizeAudio(trimmed.audio[0],-10,100,150);assert.ok(trimmed.audio[0].source_in>=0);assert.ok(trimmed.audio[0].source_in+trimmed.audio[0].end-trimmed.audio[0].start<=150);console.log('PASS: audio split, trim and source bounds');
assert.equal(E.selectionFrame(0,60,90),60);assert.equal(E.selectionFrame(75,60,90),75);assert.equal(E.selectionFrame(150,60,90),89);
const dup=E.blankPlan(10,[{start:2,end:3,text:'Koreksi'}]),ds=dup.segments[0];ds.overlays=[{id:'image',kind:'image',start:60,end:90,text:'',asset_id:'asset',layer:1,style:E.style()}];ds.audio=[{id:'audio',asset_id:'a',start:60,end:90,source_in:15,volume:.3}];
for(const [kind,id] of [['overlay','image'],['audio','audio'],['caption',ds.captions[0].id]]){const result=E.duplicateItem(dup,{kind,id,segmentId:ds.id});assert.ok(result.id!==id)}
assert.equal(ds.audio[1].start,90);assert.equal(ds.audio[1].source_in,15);assert.equal(ds.overlays[1].layer,2);ds.overlays[1].style.x=.1;assert.equal(ds.overlays[0].style.x,.5);assert.equal(ds.captions[1].words[0].start,90);
E.duplicateItem(dup,{kind:'video',id:ds.id,segmentId:ds.id});assert.equal(dup.segments.length,2);assert.notEqual(dup.segments[1].audio[0].id,ds.audio[0].id);assert.equal(E.total(dup),600);console.log('PASS: selection boundaries and independent duplicates of video, captions, images and audio');
