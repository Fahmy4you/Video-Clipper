require('./register-ts.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');
const cp = require('node:child_process');
const { motionAt, modernStyle } = require('../apps/web/src/subtitleTemplates.ts');
const root = path.resolve(__dirname, '..');
const cases = [];
for (const motion of ['none', 'fade', 'zoom', 'zoom_fade', 'down', 'down_fade'])
  for (const end of [1, 3, 9, 90])
    for (let frame = 0; frame < end; frame += 0.5) cases.push([0, end, frame, motion]);
const expected = JSON.parse(
  cp.execFileSync(
    path.join(root, '.venv/bin/python'),
    [
      '-c',
      'import json,sys;from app.subtitle_templates import motion_at;print(json.dumps([motion_at(*x) for x in json.load(sys.stdin)]))',
    ],
    {
      input: JSON.stringify(cases),
      env: { ...process.env, PYTHONPATH: path.join(root, 'backend') },
      encoding: 'utf8',
    },
  ),
);
cases.forEach((c, i) => {
  const actual = motionAt(...c);
  for (const key of ['opacity', 'scale', 'dy'])
    assert.ok(Math.abs(actual[key] - expected[i][key]) < 1e-10);
});
assert.equal(modernStyle().subtitle_template, 'sentence');
assert.equal(modernStyle().subtitle_motion, 'none');
console.log(cases.length + ' frontend/backend animation states and new-style defaults passed.');
