require('./register-ts.cjs');
const assert = require('node:assert/strict');
const {
  partsFromFrame,
  frameFromParts,
  frameLabel,
  validRange,
} = require('../apps/web/src/timeRange.ts');
for (let frame = 0; frame <= 540000; frame += 137)
  assert.equal(frameFromParts(partsFromFrame(frame)), frame);
for (const frame of [0, 29, 30, 1799, 1800, 107999, 108000, 540000])
  assert.equal(frameFromParts(partsFromFrame(frame)), frame);
assert.equal(frameLabel(300, 10), '10');
assert.equal(frameLabel(1800, 60), '01:00');
assert.equal(frameLabel(108000, 3600), '01:00:00');
for (const bad of [
  { h: '-1', m: '00', s: '00' },
  { h: '0', m: '100', s: '0' },
  { h: '0', m: '0', s: '60' },
  { h: '0', m: '', s: '0' },
])
  assert(Number.isNaN(frameFromParts(bad)));
assert(validRange(partsFromFrame(0), partsFromFrame(300), 10));
assert(!validRange(partsFromFrame(0), partsFromFrame(299), 10));
assert(!validRange(partsFromFrame(0), partsFromFrame(301), 10));
console.log('Time range frame round-trip and validation passed');

const { durationLabel, mixCapacity } = require('../apps/web/src/timeRange.ts');
assert.equal(durationLabel(2457), '1 menit 21,9 detik');
assert.equal(durationLabel(108030), '1 jam 1 detik');
for (const [seconds, capacity] of [
  [10, 1],
  [20, 2],
  [30, 3],
  [40, 4],
  [50, 5],
  [60, 5],
])
  assert.equal(mixCapacity(seconds * 30), capacity);
assert(validRange(partsFromFrame(0), partsFromFrame(36000), 2000));
assert(!validRange(partsFromFrame(0), partsFromFrame(36001), 2000));

const { compactDuration } = require('../apps/web/src/timeRange.ts');
for (const [seconds, expected] of [
  [0, '0d'],
  [59.99, '59d'],
  [60, '1m 0d'],
  [3599, '59m 59d'],
  [3600, '1j 0m 0d'],
  [6490, '1j 48m 10d'],
  [7343.041, '2j 2m 23d'],
  [18000, '5j 0m 0d'],
  [-1, '0d'],
  [Infinity, '—'],
])
  assert.equal(compactDuration(seconds), expected);
console.log('Compact duration hours/minutes/seconds passed');
