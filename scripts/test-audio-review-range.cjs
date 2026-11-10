require('./register-ts.cjs');
const assert = require('node:assert/strict');
const { initialAudioArea } = require('../apps/web/src/audioReviewRange.ts');
for (const [total, start, end, length] of [
  [300, 0, 300, 300],
  [216000, 108000, 109800, 18000],
  [216000, 0, 1800, 18000],
  [216000, 214200, 216000, 18000],
  [540000, 108000, 129600, 22500],
  [540000, 108000, 144000, 36000],
]) {
  const [a, b] = initialAudioArea(total, start, end);
  assert.equal(b - a, length);
  assert.ok(a >= 0 && b <= total);
  assert.ok(a <= start && b >= end);
  assert.ok(Number.isInteger(a) && Number.isInteger(b));
}
console.log('PASS: centered audio areas, short sources, source edges, and 10/20-minute limits');
