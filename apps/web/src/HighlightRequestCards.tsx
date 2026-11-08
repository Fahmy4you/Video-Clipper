import { durationLabel } from './timeRange';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, RefreshCw, Trash2, Loader2 } from 'lucide-react';
import { api, type Job, type Project } from './api';
import type { Proposal } from './ReviewHighlights';
import { Dialog, useConfirm } from './components/Ui';
import { ModelSelect } from './components/ModelSelect';
import { Button } from './components/ui/button';
import { SelectCheckbox } from './components/BulkSelection';
import { isPending, jobLabel, WaitingDetails } from './components/QueueStatus';
import { frameLabel } from './components/TimeRangeFields';
import './highlightRequests.css';

type RequestItem = {
  id: string;
  number: number;
  revision: number;
  status: string;
  reason: string;
  snapshot: { combo?: string };
  proposal: Proposal | null;
  job: Job | null;
};
export function HighlightRequestCards({
  project,
  refresh,
  selecting,
  selected,
  onSelect,
  view,
}: {
  project: Project;
  refresh: () => Promise<void>;
  selecting: boolean;
  selected: Set<string>;
  onSelect: (id: string) => void;
  view: 'transcription' | 'video';
}) {
  const [items, setItems] = useState<RequestItem[]>([]),
    [loading, setLoading] = useState(true);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<RequestItem | null>(null),
    [combo, setCombo] = useState('');
  const request = useRef<{ text: string; id: string } | null>(null);
  const confirm = useConfirm();
  async function reload() {
    setItems(await api<RequestItem[]>('/projects/' + project.id + '/highlight-requests'));
  }
  useEffect(() => {
    let live = true;
    const poll = async () => {
      try {
        const rows = await api<RequestItem[]>('/projects/' + project.id + '/highlight-requests');
        if (live) {
          setItems(rows);
          setError('');
        }
      } catch (e) {
        if (live) setError((e as Error).message);
      } finally {
        if (live) setLoading(false);
      }
    };
    void poll();
    const timer = setInterval(poll, 2500);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [project.id]);
  const available = items.filter((x) => x.proposal).length;
  const unmet = items.filter((x) => !x.proposal && x.status === 'unfulfilled').length;
  const failed = items.filter(
    (x) => !x.proposal && ['failed', 'cancelled'].includes(x.status),
  ).length;
  const pending = items.length - available - unmet - failed;
  async function retry() {
    if (!target || busy) return;
    const body = { revision: target.revision, ai_combo: combo };
    const text = JSON.stringify({ id: target.id, ...body });
    if (request.current?.text !== text) request.current = { text, id: crypto.randomUUID() };
    setBusy(true);
    setError('');
    try {
      await api('/highlight-requests/' + target.id + '/reanalyze', 'POST', {
        ...body,
        request_id: request.current.id,
      });
      setTarget(null);
      request.current = null;
      await reload();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {loading ? (
        <p role="status">Memuat permintaan highlight…</p>
      ) : (
        <>
          {view === 'transcription' && (
            <p className="request-summary">
              {items.length} highlight diminta · {available} tersedia · {unmet} belum terpenuhi
              {failed ? ' · ' + failed + ' gagal dibuat' : ''}
              {pending ? ' · ' + pending + ' menunggu/dianalisis' : ''}
            </p>
          )}
          {!items.length && (
            <p className="panel request-empty">
              Belum ada permintaan highlight. Gunakan Tambah highlight untuk mencari satu usulan.
            </p>
          )}
          <div className="request-grid">
            {items
              .filter(
                (item) =>
                  view === 'transcription' ||
                  (item.proposal?.job_id && item.proposal.status !== 'ready'),
              )
              .map((item) => {
                const p = item.proposal;
                const working = !p && !!item.job && isPending(item.job);
                const label = p
                  ? 'Usulan tersedia'
                  : item.status === 'unfulfilled'
                    ? 'Belum terpenuhi'
                    : working && item.job
                      ? jobLabel(item.job)
                      : item.status === 'cancelled'
                        ? 'Dibatalkan'
                        : 'Gagal dibuat';
                return (
                  <article className="panel request-card" key={item.id}>
                    <header>
                      {selecting && p && p.status !== 'ready' && (
                        <SelectCheckbox
                          label={'Pilih ' + p.title}
                          checked={selected.has(p.id)}
                          disabled={
                            !!p.job_id &&
                            [
                              'queued',
                              'running',
                              'waiting_service',
                              'waiting_quota',
                              'waiting_network',
                            ].includes(p.status)
                          }
                          onChange={() => onSelect(p.id)}
                        />
                      )}
                      <small>Highlight transkrip #{item.number}</small>
                      <span className="request-status">{label}</span>
                    </header>
                    <h2>{p?.title || 'Usulan highlight #' + item.number}</h2>
                    <p className="request-description">
                      {p?.summary ||
                        item.reason ||
                        (working
                          ? 'Sumber dan transkrip sedang disiapkan atau dianalisis.'
                          : 'Usulan belum berhasil tersedia. Kamu dapat memilih combo dan mencoba analisis ulang.')}
                    </p>
                    {p && (
                      <p className="request-time">
                        {frameLabel(p.start, project.duration)}–
                        {frameLabel(p.end, project.duration)} · {durationLabel(p.end - p.start)}
                      </p>
                    )}
                    {working && item.job && (
                      <>
                        <progress max={100} value={item.job.progress || 0} />
                        <WaitingDetails
                          job={item.job}
                          onCheck={() => {
                            void api('/jobs/' + item.job!.id + '/check', 'POST')
                              .then(reload)
                              .catch((e) => setError(e.message));
                          }}
                        />
                      </>
                    )}
                    {p && p.status !== 'review' && (
                      <small>
                        Status video:{' '}
                        {p.status === 'ready'
                          ? 'Siap diedit'
                          : p.status === 'failed'
                            ? 'Penyusunan gagal — buka Detail'
                            : p.status}
                      </small>
                    )}
                    <footer>
                      {p ? (
                        <Link
                          className="icon-button"
                          title="Detail"
                          aria-label={'Detail ' + p.title}
                          to={'/transcriptions/' + project.id + '/highlights/' + p.id}
                        >
                          <ArrowUpRight size={18} />
                        </Link>
                      ) : (
                        <button
                          type="button"
                          className="icon-button"
                          title="Analisis ulang"
                          aria-label={'Analisis ulang highlight #' + item.number}
                          disabled={working || busy}
                          onClick={() => {
                            setTarget(item);
                            setCombo(item.snapshot.combo || project.ai_combo || '');
                            setError('');
                          }}
                        >
                          <RefreshCw size={18} />
                        </button>
                      )}
                      <button
                        type="button"
                        className="icon-button danger"
                        title="Hapus highlight"
                        aria-label={'Hapus highlight #' + item.number}
                        disabled={
                          working ||
                          busy ||
                          (!!p &&
                            (p.status === 'ready' ||
                              [
                                'queued',
                                'running',
                                'cancelling',
                                'waiting_service',
                                'waiting_quota',
                                'waiting_network',
                              ].includes(p.status)))
                        }
                        onClick={async () => {
                          if (
                            !(await confirm({
                              title: 'Hapus highlight?',
                              description:
                                'Item ini akan dihapus. Video sumber, transkrip, dan highlight lain tetap tersedia.',
                              danger: true,
                              confirmLabel: 'Hapus',
                            }))
                          )
                            return;
                          setBusy(true);
                          try {
                            await api(
                              '/highlight-requests/' + item.id + '?revision=' + item.revision,
                              'DELETE',
                            );
                            await reload();
                            await refresh();
                          } catch (e) {
                            setError((e as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <Trash2 size={18} />
                      </button>
                    </footer>
                  </article>
                );
              })}
          </div>
        </>
      )}
      {error && !target && (
        <p role="alert" className="notice">
          {error}
        </p>
      )}
      <Dialog
        open={!!target}
        onClose={() => {
          if (!busy) setTarget(null);
        }}
        title={'Analisis ulang highlight #' + (target?.number || '')}
        description="Percobaan ini memperbarui item yang sama menggunakan sumber dan transkrip tersimpan."
        footer={
          <>
            <Button variant="secondary" disabled={busy} onClick={() => setTarget(null)}>
              Batal
            </Button>
            <Button disabled={busy || !combo} onClick={() => void retry()}>
              {busy ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}Analisis
              ulang
            </Button>
          </>
        }
      >
        <div className="mg-dialog-form">
          <p>{target?.reason || 'Pilih combo untuk mencoba kembali.'}</p>
          <ModelSelect value={combo} onChange={setCombo} disabled={busy} />
          {error && <p role="alert">{error}</p>}
        </div>
      </Dialog>
    </>
  );
}
