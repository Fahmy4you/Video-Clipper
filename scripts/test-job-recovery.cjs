require('./register-ts.cjs');
const assert = require('node:assert/strict');
const { recoveryState } = require('../apps/web/src/jobRecovery.ts');

const job = (id, time, status, provider, extra = {}) => ({
  id,
  project_id: 'project',
  clip_id: null,
  kind: 'analysis',
  created_at: new Date(Date.UTC(2026, 10, 7, time)).toISOString(),
  status,
  payload: provider ? { provider } : {},
  result: {},
  ...extra,
});

const attempts = [
  job('oldest', 1, 'failed'),
  job('older', 2, 'failed'),
  job('latest-legacy', 3, 'waiting_service'),
];
assert.deepEqual(
  recoveryState(attempts).candidates.map((j) => j.id),
  ['latest-legacy'],
);
assert.equal(recoveryState(attempts).history.length, 2);
assert.deepEqual(recoveryState([...attempts].reverse()), recoveryState(attempts));

for (const status of ['queued', 'running', 'succeeded', 'failed', 'cancelled']) {
  const state = recoveryState([...attempts, job('router', 4, status, '9router')]);
  assert.equal(state.candidates.length, 0, status);
  assert.equal(state.history.length, 3);
}

assert.equal(
  recoveryState([job('legacy-success', 5, 'succeeded'), ...attempts]).candidates.length,
  0,
);
assert.equal(
  recoveryState([
    job('migrated', 5, 'cancelled', undefined, { result: { successor_job_id: 'not-polled-yet' } }),
  ]).candidates.length,
  0,
);

const first = job('build-one', 1, 'failed', undefined, {
  kind: 'build_highlight',
  payload: { proposal_id: 'one' },
});
const second = job('build-two', 2, 'failed', undefined, {
  kind: 'build_highlight',
  payload: { proposal_id: 'two' },
});
assert.equal(recoveryState([first, second]).candidates.length, 2);
assert.equal(
  recoveryState([
    first,
    second,
    {
      ...first,
      id: 'new-one',
      created_at: second.created_at,
      status: 'succeeded',
      payload: { proposal_id: 'one', provider: '9router' },
    },
  ]).candidates.length,
  1,
);
const unrelated = job('export', 6, 'succeeded', undefined, { kind: 'export' });
assert.deepEqual(
  recoveryState([unrelated, ...attempts]).candidates.map((j) => j.id),
  ['latest-legacy'],
);
const originalOrder = attempts.map((j) => j.id);
recoveryState(attempts);
assert.deepEqual(
  attempts.map((j) => j.id),
  originalOrder,
);
console.log(
  'PASS: latest recovery per target; old retries and migrated/superseded attempts never create duplicate forms',
);
