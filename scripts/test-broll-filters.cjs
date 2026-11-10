require('./register-ts.cjs');
const assert = require('node:assert/strict');
const { brollOptions, matchesBroll, GLOBAL_SOURCE } = require('../apps/web/src/brollFilters.ts');
const assets = [
  {
    id: '1',
    title: 'Pasar',
    explain: 'Berita',
    scope: 'global',
    hashtags: ['saham'],
    hashtag_ids: ['s'],
    instansi_ids: [],
    instansi_names: [],
  },
  {
    id: '2',
    title: 'Ekonomi',
    explain: 'Pasar Indonesia',
    scope: 'instansi',
    hashtags: ['ekonomi', 'saham'],
    hashtag_ids: ['e', 's'],
    instansi_ids: ['b', 'a'],
    instansi_names: ['Alpha', 'Beta'],
  },
  {
    id: '3',
    title: 'Lain',
    explain: '',
    scope: 'instansi',
    hashtags: ['alam'],
    hashtag_ids: ['n'],
    instansi_ids: ['b'],
    instansi_names: ['Beta'],
  },
];
const ids = (q, tags, owners) =>
  assets.filter((a) => matchesBroll(a, q, tags, owners)).map((a) => a.id);
assert.deepEqual(ids('', [], []), ['1', '2', '3']);
assert.deepEqual(ids('  PASAR  ', [], []), ['1', '2']);
assert.deepEqual(ids('#saham', [], []), ['1', '2']);
assert.deepEqual(ids('', ['e', 'n'], []), ['2', '3']);
assert.deepEqual(ids('', ['s'], ['a']), ['2']);
assert.deepEqual(ids('', ['s'], [GLOBAL_SOURCE, 'a']), ['1', '2']);
assert.deepEqual(ids('', [], ['a', 'b']), ['2', '3']);
assert.deepEqual(ids('', ['n'], ['a']), []);
const options = brollOptions(assets, [
  { id: 'b', name: 'Beta' },
  { id: 'a', name: 'Alpha' },
]);
assert.deepEqual(
  options.hashtags.map((o) => o.id),
  ['n', 'e', 's'],
);
assert.equal(options.instansi.filter((o) => o.id === 'b').length, 1);
assert.ok(options.instansi.some((o) => o.id === GLOBAL_SOURCE));
assert.deepEqual(
  assets.map((a) => a.id),
  ['1', '2', '3'],
);
console.log(
  'Broll multi-filter intersection, union, Global, search, option deduplication, and stable order passed.',
);

assert.equal(options.instansi.find((o) => o.id === 'b').label, 'Beta');
