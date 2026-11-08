import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Loader2, RefreshCw } from 'lucide-react';
import { api, type Project, type Job } from './api';
import { Dialog } from './components/Ui';
import { ModelSelect } from './components/ModelSelect';
import { recoveryState } from './jobRecovery';
import { jobLabel, kindLabel } from './components/QueueStatus';
import './recovery.css';
import {
  TimeRangeFields,
  partsFromFrame,
  frameFromParts,
  validRange,
} from './components/TimeRangeFields';
import { Button } from './components/ui/button';

export function ProposalSearch({
  project,
  onComplete,
}: {
  project: Project;
  onComplete?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [timed, setTimed] = useState(false);
  const [fixed, setFixed] = useState(true);
  const [start, setStart] = useState(partsFromFrame(0));
  const [end, setEnd] = useState(partsFromFrame(Math.floor(Math.min(60, project.duration) * 30)));
  const [combo, setCombo] = useState(project.ai_combo || '');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<{ text: string; id: string } | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    if (!open) setCombo(project.ai_combo || '');
  }, [project.ai_combo, open]);
  async function submit() {
    setBusy(true);
    setError('');
    const body = {
      ai_combo: combo,
      highlight_count: 1,
      policy_version: 2,
      additional_prompt: prompt,
      time_range: timed
        ? { start_frame: frameFromParts(start), end_frame: frameFromParts(end), fix_time: fixed }
        : null,
    };
    const text = JSON.stringify(body);
    if (request.current?.text !== text) request.current = { text, id: crypto.randomUUID() };
    try {
      await api('/projects/' + project.id + '/searches', 'POST', {
        ...body,
        request_id: request.current.id,
      });
      setOpen(false);
      setPrompt('');
      setTimed(false);
      setFixed(true);
      setStart(partsFromFrame(0));
      setEnd(partsFromFrame(Math.floor(Math.min(60, project.duration) * 30)));
      request.current = null;
      onComplete?.();
      navigate('/transcriptions/' + project.id);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button type="button" onClick={() => setOpen(true)}>
        <Plus size={16} />
        Tambah highlight
      </Button>
      <Dialog
        open={open}
        onClose={() => {
          if (!busy) setOpen(false);
        }}
        title="Tambah highlight"
        description="Gunakan transkrip tersimpan untuk mencari topik atau bagian waktu tertentu."
        footer={
          <>
            <Button variant="secondary" disabled={busy} onClick={() => setOpen(false)}>
              Batal
            </Button>
            <Button
              form="proposal-search"
              disabled={busy || !combo || (timed && !validRange(start, end, project.duration))}
            >
              {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}Buat highlight
            </Button>
          </>
        }
      >
        <form
          id="proposal-search"
          className="mg-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <ModelSelect value={combo} onChange={setCombo} disabled={busy} />
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={timed}
              onChange={(e) => {
                setTimed(e.target.checked);
                if (e.target.checked) setFixed(true);
              }}
            />
            Tentukan waktu
          </label>
          {timed && (
            <>
              <TimeRangeFields
                start={start}
                end={end}
                duration={project.duration}
                onStart={setStart}
                onEnd={setEnd}
              />
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={fixed}
                  onChange={(e) => setFixed(e.target.checked)}
                />
                Fix time
              </label>
              <p className="field-help">
                {fixed
                  ? 'Waktu hasil mengikuti rentang ini persis.'
                  : 'AI boleh menyesuaikan masing-masing batas hingga 60 detik agar konteks utuh.'}
              </p>
            </>
          )}
          <label>
            Prompt tambahan — opsional
            <textarea
              maxLength={4000}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Contoh: Sekitar 19:20–20:20 membahas memulai bisnis. Cari bagian dengan percakapan yang utuh."
            />
          </label>
          <p className="field-help">
            Waktu atau arahan yang kamu isi boleh menggunakan bagian lama. Jika keduanya kosong, AI
            menghindari bagian yang sudah dipakai.
          </p>
          {error && (
            <p className="notice" role="alert">
              {error}
            </p>
          )}
        </form>
      </Dialog>
    </>
  );
}

export function RouterRecovery({ job, onComplete }: { job: Job; onComplete: () => Promise<void> }) {
  const [combo, setCombo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (
    job.payload.provider === '9router' ||
    !!job.result.successor_job_id ||
    ['running', 'cancelling', 'succeeded'].includes(job.status) ||
    !['analysis', 'mix', 'build_highlight'].includes(job.kind)
  )
    return null;
  return (
    <section className="panel router-recovery" aria-label="Lanjutkan pekerjaan lama">
      <header>
        <RefreshCw size={16} />
        <strong>Lanjutkan pekerjaan lama</strong>
      </header>
      <p>Pekerjaan lama dapat dilanjutkan memakai sumber dan transkrip yang sudah tersimpan.</p>
      <ModelSelect value={combo} onChange={setCombo} disabled={busy} />
      <Button
        disabled={busy || !combo}
        onClick={async () => {
          setBusy(true);
          setError('');
          try {
            await api('/jobs/' + job.id + '/router', 'POST', { ai_combo: combo });
            await onComplete();
          } catch (error) {
            setError((error as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <RefreshCw size={16} />
        Lanjutkan dengan 9Router
      </Button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

export function RouterRecoveryList({
  jobs,
  onComplete,
}: {
  jobs: Job[];
  onComplete: () => Promise<void>;
}) {
  const { candidates, history } = recoveryState(jobs);
  return (
    <>
      {candidates.map((job) => (
        <RouterRecovery key={job.id} job={job} onComplete={onComplete} />
      ))}
      {history.length > 0 && (
        <details className="panel recovery-history">
          <summary>Riwayat percobaan lama ({history.length})</summary>
          <ul>
            {history.map((job) => (
              <li key={job.id}>
                <span>
                  {kindLabel(job.kind)} · {jobLabel(job)}
                </span>
                <time dateTime={job.created_at}>
                  {new Date(job.created_at).toLocaleString('id-ID')}
                </time>
                {job.result.successor_job_id && <span>Sudah dilanjutkan melalui 9Router.</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
