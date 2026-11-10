import { useId, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Download, History, Loader2 } from 'lucide-react';
import { Dialog } from './components/Ui';
import { isPending, jobLabel } from './components/QueueStatus';
import { formats, type Plan } from './editorModel';
import { type Job } from './api';
type Config = { mode: string; local_dir: string | null; ready: boolean; error: string | null };
export function ExportDialog({
  open,
  onClose,
  ratio,
  plan,
  jobs,
  config,
  start,
}: {
  open: boolean;
  onClose: () => void;
  ratio: string;
  plan: Plan | undefined;
  jobs: Job[];
  config: Config | null;
  start: (resolution: number) => Promise<void>;
}) {
  const [resolution, setResolution] = useState(1080),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const submitting = useRef(false);
  const resolutionId = useId();
  const f = formats.find((f) => f.id === ratio) || formats[0],
    width = (f.width * resolution) / 1080,
    height = (f.height * resolution) / 1080;
  const filtered = plan?.filters?.some((f) => f.strength > 0 && f.targets.length);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      className="export-dialog"
      title="Ekspor video"
      description="Pilih resolusi MP4 sesuai kebutuhan."
      footer={
        <>
          <button className="button secondary" onClick={onClose}>
            Tutup
          </button>
          <button
            className="button primary"
            aria-label={busy ? 'Memulai ekspor…' : 'Mulai ekspor'}
            disabled={busy || !config?.ready || !plan}
            onClick={async () => {
              if (submitting.current) return;
              submitting.current = true;
              setBusy(true);
              setError('');
              try {
                await start(resolution);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                submitting.current = false;
                setBusy(false);
              }
            }}
          >
            {busy ? (
              <Loader2 size={16} className="spin" aria-hidden="true" />
            ) : (
              <Download size={16} aria-hidden="true" />
            )}
            <span role="status">{busy ? 'Memulai ekspor…' : 'Mulai ekspor'}</span>
          </button>
        </>
      }
    >
      <div className="export-resolution">
        <label htmlFor={resolutionId}>Resolusi</label>
        <select
          id={resolutionId}
          value={resolution}
          onChange={(e) => setResolution(+e.target.value)}
        >
          <option value={360}>360p — ringan, cek hasil edit</option>
          <option value={720}>720p — sedang</option>
          <option value={1080}>1080p — tinggi, hasil akhir</option>
        </select>
      </div>
      <ul className="export-output" aria-label="Informasi hasil ekspor">
        <li>
          <strong>Dimensi:</strong> {width} × {height} px
        </li>
        <li>
          <strong>Rasio:</strong> {ratio}
        </li>
        <li>
          <strong>Frame rate:</strong> 30 fps
        </li>
      </ul>
      <p className="export-destination muted">
        {config?.mode === 'local'
          ? 'Tersimpan otomatis di ' + config.local_dir
          : 'MP4 diunduh otomatis melalui browser setelah selesai.'}
      </p>
      {filtered && resolution < 1080 && (
        <p className="field-help">
          Filter Tajam diproses pada resolusi komposisi. Ekspor beresolusi rendah tetap dapat
          membutuhkan waktu cukup lama.
        </p>
      )}
      {(error || config?.error) && (
        <p className="export-error" role="alert">
          {error || config?.error}
        </p>
      )}
      <details className="export-history">
        <summary>
          <History size={16} />
          <span>Riwayat ekspor ({jobs.length})</span>
          <ChevronRight size={16} className="export-history-closed" aria-hidden="true" />
          <ChevronDown size={16} className="export-history-open" aria-hidden="true" />
        </summary>
        <div className="export-history-content">
          {jobs.length === 0 && <p className="muted">Belum ada ekspor.</p>}
          {jobs.map((j) => (
            <article key={j.id}>
              <strong>
                {j.kind === 'preview'
                  ? 'Arsip preview · resolusi rendah'
                  : (j.result.resolution || j.payload.resolution || 1080) + 'p'}{' '}
                · revisi {j.result.revision || (j.payload.revision as number)}
              </strong>
              <span>
                {isPending(j)
                  ? jobLabel(j) + ' · ' + j.progress + '%'
                  : j.status === 'succeeded'
                    ? j.result.local_path
                      ? 'Tersimpan di ' + j.result.local_path
                      : 'Siap diunduh'
                    : j.error || jobLabel(j)}
              </span>
              {j.status === 'succeeded' && (
                <a
                  className="button secondary"
                  href={
                    j.kind === 'preview'
                      ? j.result.url
                      : j.result.download_url || '/api/exports/' + j.id + '/download'
                  }
                  download
                >
                  <Download size={14} />
                  {j.kind === 'preview' ? 'Unduh arsip preview' : 'Unduh MP4'}
                </a>
              )}
            </article>
          ))}
        </div>
      </details>
    </Dialog>
  );
}
