import { useEffect, useState } from 'react';
import { ListOrdered, Loader2, Clock3, RefreshCw } from 'lucide-react';
import { api, type Job } from '../api';
import { compactDuration } from '../timeRange';
import '../queue.css';
export const pendingStatuses = [
  'queued',
  'running',
  'cancelling',
  'waiting_quota',
  'waiting_service',
  'waiting_network',
];
export const isPending = (job: Job) => pendingStatuses.includes(job.status);
export const isWaiting = (job: Job) =>
  ['waiting_quota', 'waiting_service', 'waiting_network'].includes(job.status);
export const kindLabel = (kind: string) =>
  ({
    subtitle_refine: 'Perbaikan subtitle',
    build_highlight: 'Menyusun highlight',
    analysis: 'Pembuatan highlight',
    mix: 'Penyusunan Mix',
    preview: 'Render preview',
    export: 'Ekspor',
    editor_media: 'Persiapan preview',
    audio_import: 'Impor audio',
    review_audio: 'Persiapan audio sumber',
    library: 'Persiapan koleksi',
  })[kind] || kind;
export function jobLabel(job: Job) {
  return job.status === 'queued'
    ? 'Menunggu giliran' + (job.queue_position ? ' #' + job.queue_position : '')
    : job.status === 'waiting_quota'
      ? 'Menunggu pembatasan 9Router'
      : job.status === 'waiting_service'
        ? job.stage || 'Menunggu layanan'
        : job.status === 'cancelling'
          ? 'Membatalkan…'
          : job.status === 'succeeded'
            ? 'Selesai'
            : job.status === 'failed'
              ? 'Gagal'
              : job.status === 'cancelled'
                ? 'Dibatalkan'
                : job.stage || 'Memproses';
}
export function WaitingDetails({
  job,
  onCheck,
  disabled = false,
}: {
  job: Job;
  onCheck: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="queue-wait-details">
      <span>
        {job.wait_reason}
        {job.next_attempt_at
          ? ' Pemeriksaan berikutnya: ' + new Date(job.next_attempt_at).toLocaleString('id-ID')
          : isWaiting(job)
            ? ' Waktu pemulihan belum diketahui.'
            : ''}
      </span>
      {isWaiting(job) && (
        <button
          type="button"
          className="button secondary"
          disabled={
            disabled || (!!job.next_attempt_at && Date.parse(job.next_attempt_at) > Date.now())
          }
          onClick={onCheck}
        >
          <RefreshCw size={14} />
          Periksa lagi
        </button>
      )}
    </div>
  );
}
export function QueueOverview() {
  const [worker, setWorker] = useState<{ status: string; message: string } | null>(null);
  const [queue, setQueue] = useState<{ active: Job | null; waiting: Job[] } | null>(null),
    [error, setError] = useState(false);
  useEffect(() => {
    let live = true;
    const refresh = () =>
      api<{ active: Job | null; waiting: Job[]; worker?: { status: string; message: string } }>(
        '/queue',
      )
        .then((q) => {
          if (live) {
            setQueue(q);
            setWorker(q.worker || null);
            setError(false);
          }
        })
        .catch(() => {
          if (live) setError(true);
        });
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  return (
    <aside className="queue-overview" aria-label="Antrean pekerjaan">
      <ListOrdered size={18} />
      <div>
        <strong>Satu pekerjaan aktif pada satu waktu</strong>
        <p>
          {worker && worker.status !== 'ready' && worker.status !== 'unknown' ? (
            worker.message
          ) : error ? (
            'Status antrean belum dapat dimuat. Akan diperiksa kembali.'
          ) : !queue ? (
            'Memuat antrean…'
          ) : queue.active ? (
            <>
              <Loader2 size={13} className="spin" />
              {kindLabel(queue.active.kind)} · {jobLabel(queue.active)}
            </>
          ) : (
            'Tidak ada pekerjaan yang sedang diproses.'
          )}
        </p>
        {queue?.active && <JobMetrics job={queue.active} />}
      </div>
      {queue && (
        <span>
          <Clock3 size={14} />
          {queue.waiting.length} menunggu
        </span>
      )}
    </aside>
  );
}

export function JobMetrics({ job }: { job: Job }) {
  const m = job.telemetry;
  if (!m) return null;
  const n = (key: string) => (typeof m[key] === 'number' ? (m[key] as number) : 0);
  return (
    <div className="job-metrics">
      {n('subtitle_total') > 0 && (
        <span>
          Subtitle {n('subtitle_completed')}/{n('subtitle_total')} bagian · Whisper small
        </span>
      )}
      {n('chunks_total') > 0 && (
        <span>
          Transkripsi {n('chunks_completed')}/{n('chunks_total')} bagian ·{' '}
          {compactDuration(n('processed_seconds'))} / {compactDuration(n('total_seconds'))}
        </span>
      )}
      {n('download_total_bytes') > 0 && (
        <span>
          Unduh {(n('downloaded_bytes') / 1024 ** 2).toFixed(0)} /{' '}
          {(n('download_total_bytes') / 1024 ** 2).toFixed(0)} MB
          {n('download_speed') > 0
            ? ' · ' + (n('download_speed') / 1024 ** 2).toFixed(1) + ' MB/detik'
            : ''}
        </span>
      )}
      {n('mix_batches_total') > 0 && (
        <span>
          Mix highlight {n('mix_highlight')}/{n('mix_highlights_total')} · batch {n('mix_batch')}/
          {n('mix_batches_total')} · {n('mix_candidates')} kandidat
        </span>
      )}
      {n('peak_memory_bytes') > 0 && (
        <span>Puncak RAM {(n('peak_memory_bytes') / 1024 ** 2).toFixed(0)} MB</span>
      )}
      {n('elapsed_seconds') > 0 && (
        <span>Waktu pengerjaan {compactDuration(n('elapsed_seconds'))}</span>
      )}
      {n('eta_seconds') > 0 && job.status === 'running' && (
        <span>Perkiraan tersisa {compactDuration(n('eta_seconds'))}</span>
      )}
    </div>
  );
}
