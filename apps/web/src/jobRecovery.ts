import type { Job } from './api';

const recoveryKinds = new Set(['analysis', 'mix', 'build_highlight']);
const recoverableStatuses = new Set([
  'queued',
  'failed',
  'cancelled',
  'waiting_quota',
  'waiting_service',
  'waiting_network',
]);

function target(job: Job) {
  const component =
    job.kind === 'build_highlight'
      ? job.payload.proposal_id || job.clip_id || job.id
      : job.clip_id || 'project';
  return [job.project_id, job.kind, component].join(':');
}

export function recoveryState(jobs: Job[]) {
  const relevant = jobs
    .filter((job) => recoveryKinds.has(job.kind))
    .slice()
    .sort(
      (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id.localeCompare(a.id),
    );
  const latest = new Map<string, Job>();
  for (const job of relevant) {
    if (!latest.has(target(job))) latest.set(target(job), job);
  }

  const candidates = [...latest.values()].filter(
    (job) =>
      job.payload.provider !== '9router' &&
      !job.result.successor_job_id &&
      recoverableStatuses.has(job.status),
  );
  const candidateIds = new Set(candidates.map((job) => job.id));
  const history = relevant.filter(
    (job) =>
      job.payload.provider !== '9router' &&
      !candidateIds.has(job.id) &&
      !['running', 'cancelling'].includes(job.status),
  );
  return { candidates, history };
}
