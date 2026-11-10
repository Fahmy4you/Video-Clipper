import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type Job } from './api';
import { isPending } from './components/QueueStatus';

export function exportProgress(job: Job) {
  if (job.status === 'running') return `Mengekspor… ${job.progress}%`;
  if (job.status === 'cancelling') return 'Membatalkan ekspor…';
  if (job.status === 'queued') return 'Ekspor menunggu giliran';
  return job.wait_reason || job.stage || 'Ekspor sedang menunggu';
}

export function useExportQueue() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [known, setKnown] = useState(false);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const generation = useRef(0);
  const live = useRef(false);
  const refresh = useCallback(async () => {
    const request = ++generation.current;
    setChecking(true);
    try {
      const queue = await api<{ active: Job | null; waiting: Job[] }>('/queue');
      if (!live.current || request !== generation.current) return;
      setJobs(
        [...(queue.active ? [queue.active] : []), ...queue.waiting].filter(
          (j) => j.kind === 'export' && isPending(j),
        ),
      );
      setKnown(true);
      setError('');
    } catch {
      if (!live.current || request !== generation.current) return;
      setKnown(false);
      setError('Status ekspor belum dapat diperiksa. Periksa ulang sebelum memulai ekspor.');
    } finally {
      if (live.current && request === generation.current) setChecking(false);
    }
  }, []);
  const accepted = useCallback((job: Job) => {
    ++generation.current; // Ignore a queue response started before submission.
    setChecking(false);
    setKnown(true);
    setError('');
    setJobs((old) => [job, ...old.filter((j) => j.id !== job.id)]);
  }, []);
  useEffect(() => {
    live.current = true;
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    const changed = () => void refresh();
    window.addEventListener('vc-export-queue', changed);
    return () => {
      live.current = false;
      ++generation.current;
      clearInterval(timer);
      window.removeEventListener('vc-export-queue', changed);
    };
  }, [refresh]);
  return { jobs, known, error, checking, refresh, accepted, blocked: !known || jobs.length > 0 };
}
