require('./register-ts.cjs');
const assert = require('assert/strict'),
  cp = require('child_process'),
  E = require('../apps/web/src/editorModel.ts'),
  B = require('../apps/web/src/boundaries.ts');
const p = E.blankPlan(5),
  s = p.segments[0],
  br = {
    id: 'br',
    asset_id: 'asset',
    start: 30,
    end: 120,
    source_in: 60,
    reason: 'test',
    transform: s.transform,
    transition_in: { kind: 'flash', frames: 12, sound: 'camera_shutter' },
    transition_out: { kind: 'crossfade', frames: 12 },
  };
s.broll = [br];
B.normalizeTransitions(p);
const python = JSON.parse(
  cp.execFileSync(
    '.venv/bin/python',
    [
      '-c',
      'import sys,json;from app.boundaries import normalize,boundaries,events;p=json.load(sys.stdin);print(json.dumps(dict(plan=normalize(p),events=[{k:e[k] for k in ("id","frame","kind","half","fallback")} for e in events(p)])))',
    ],
    { env: { ...process.env, PYTHONPATH: 'backend' }, input: JSON.stringify(p), encoding: 'utf8' },
  ),
);
assert.deepEqual(python.plan, p);
assert.deepEqual(
  B.boundaryEvents(p).map((e) => ({
    id: e.id,
    frame: e.frame,
    kind: e.kind,
    half: e.half,
    fallback: e.fallback,
  })),
  python.events,
);
const before = JSON.stringify(p);
E.splitSegment(p, 29);
assert.equal(JSON.stringify(p), before);
E.splitSegment(p, 60);
assert.equal(p.segments.length, 2);
B.normalizeTransitions(p);
assert.equal(B.visualSpans(p).filter((s) => s.kind === 'broll').length, 1);
assert.equal(B.boundaries(p).filter((e) => e.before && e.after).length, 2);
const q = E.blankPlan(5);
B.normalizeTransitions(q);
E.splitSegment(q, 30);
B.normalizeTransitions(q);
assert.equal(q.segments[0].duration, 30);
const initial = JSON.stringify(q);
E.trimSegment(q, q.segments[0].id, 0, 29, []);
assert.equal(JSON.stringify(q), initial);
const b = B.boundaries(p).find((e) => e.value.kind === 'flash');
assert.equal(b.frame, 30);
assert.equal(B.visualLayers(p, 30)[0].span.kind, 'broll');
const d = E.blankPlan(6);
d.segments[0].broll = [structuredClone(br)];
B.normalizeTransitions(d);
const oldId = d.segments[0].id;
E.duplicateItem(d, { kind: 'video', id: oldId, segmentId: oldId });
B.normalizeTransitions(d);
assert.equal(B.boundaries(d).filter((e) => e.value.kind === 'flash').length, 2);
console.log(
  'PASS: TS/Python boundary parity, 29/30-frame split/trim guards, hidden slicing, duplicate effects, stable identities',
);

const linked = E.blankPlan(6);
linked.segments[0].broll = [structuredClone(br)];
B.normalizeTransitions(linked);
E.splitSegment(linked, 60);
B.normalizeTransitions(linked);
const linkedBefore = JSON.stringify(linked);
E.splitBroll(linked, linked.segments[0].broll[0].id, 45);
assert.equal(JSON.stringify(linked), linkedBefore);
E.splitBroll(linked, linked.segments[0].broll[0].id, 60);
B.normalizeTransitions(linked);
assert.equal(B.visualSpans(linked).filter((s) => s.kind === 'broll').length, 2);
assert(
  B.boundaries(linked).some(
    (e) => e.before?.kind === 'broll' && e.after?.kind === 'broll' && e.value.kind === 'none',
  ),
);
console.log('PASS: explicit B-roll split across internally sliced podcast segments');
