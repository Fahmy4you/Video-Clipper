import { useState } from 'react';
import { Download, History, Loader2 } from 'lucide-react';
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
  const f = formats.find((f) => f.id === ratio) || formats[0],
    width = (f.width * resolution) / 1080,
    height = (f.height * resolution) / 1080;
  const filtered = plan?.filters?.some((f) => f.strength > 0 && f.targets.length);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Ekspor video"
      description="Pilih resolusi MP4 sesuai kebutuhan."
      footer={
        <>
          <button className="button secondary" onClick={onClose}>
            Tutup
          </button>
          <button
            className="button primary"
            disabled={busy || !config?.ready || !plan}
            onClick={async () => {
              setBusy(true);
              setError('');
              try {
                await start(resolution);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <Loader2 size={16} className="spin" /> : <Download size={16} />}Mulai ekspor
          </button>
        </>
      }
    >
      <label className="export-resolution">
        Resolusi
        <select value={resolution} onChange={(e) => setResolution(+e.target.value)}>
          <option value={360}>360p — ringan, cek hasil edit</option>
          <option value={720}>720p — sedang</option>
          <option value={1080}>1080p — tinggi, hasil akhir</option>
        </select>
      </label>
      <p>
        {width} × {height} px · {ratio} · 30 fps
      </p>
      <p className="muted">
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
      {(error || config?.error) && <p role="alert">{error || config?.error}</p>}
      <details className="export-history">
        <summary>
          <History size={16} />
          Riwayat ekspor ({jobs.length})
        </summary>
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
      </details>
    </Dialog>
  );
}
