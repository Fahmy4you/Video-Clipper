require('./register-ts.cjs');
const fs = require('fs'),
  path = require('path'),
  Module = require('module'),
  assert = require('node:assert/strict'),
  cp = require('child_process'),
  ts = require('../apps/web/node_modules/typescript');
function load(name) {
  const file = path.resolve(__dirname, '../apps/web/src/' + name + '.ts'),
    m = new Module(file, module);
  m._compile(
    ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    file,
  );
  return m.exports;
}
const E = load('editorModel'),
  S = load('Sharpener'),
  p = E.blankPlan(10),
  f = {
    id: 'f',
    kind: 'sharpen',
    start: 60,
    end: 150,
    strength: 25,
    targets: ['image', 'broll', 'podcast'],
  };
p.filters = [f];
E.splitSegment(p, 90);
assert.deepEqual(p.filters, [f]);
p.segments.reverse();
assert.equal(p.filters[0].start, 60);
E.splitFilter(p, 'f', 100);
assert.equal(p.filters.length, 2);
const copy = E.duplicateItem(p, { kind: 'filter', segmentId: '', id: 'f' });
assert(copy && copy.id !== 'f');
p.filters.at(-1).strength = 80;
assert.equal(E.filterStrength(p, 'broll', 70), 80);
p.segments.splice(1, 1);
E.clampFilters(p);
assert(p.filters.every((f) => f.end <= E.total(p)));
const a = new Uint8ClampedArray(8 * 8 * 4);
for (let i = 0; i < a.length; i++) a[i] = (i * 73) % 256;
const cases = [0, 25, 100].map((s) => [...S.sharpenPixels(a, 8, 8, s)]),
  expected = JSON.parse(
    cp.execFileSync(
      path.resolve(__dirname, '../.venv/bin/python'),
      [
        '-c',
        'import json,sys,numpy as np;from PIL import Image;from app.visual_filters import sharpen_image;a=np.array(json.load(sys.stdin),dtype=np.uint8).reshape(8,8,4);print(json.dumps([np.asarray(sharpen_image(Image.fromarray(a),s)).ravel().tolist() for s in [0,25,100]]))',
      ],
      {
        cwd: path.resolve(__dirname, '..'),
        env: { ...process.env, PYTHONPATH: 'backend' },
        input: JSON.stringify([...a]),
        encoding: 'utf8',
      },
    ),
  );
cases.forEach((v, i) => assert(Math.max(...v.map((x, j) => Math.abs(x - expected[i][j]))) <= 1));
console.log('PASS: timeline filter lifecycle, max strength, alpha-aware CPU/Python pixel parity');
