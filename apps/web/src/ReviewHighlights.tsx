import { useNavigate } from 'react-router-dom';
import { durationLabel } from './timeRange';
import { HighlightRequestCards } from './HighlightRequestCards';
import { ProposalDetail } from './ProposalDetail';
import { ProposalSearch, RouterRecoveryList } from './ProposalSearch';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  ExternalLink,
  FileText,
  Settings2,
  Play,
  Copy,
  Pencil,
  Trash2,
  Loader2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { api, stamp, type Project, type Clip, type Job } from './api';
import { type Ratio } from './editorModel';
import { Button } from './components/ui/button';
import { Dialog, useConfirm, ActionMenu, ActionItem } from './components/Ui';
import {
  SelectionToggle,
  SelectCheckbox,
  useBulkSelection,
  BulkBar,
} from './components/BulkSelection';
import { isPending, jobLabel, kindLabel, WaitingDetails } from './components/QueueStatus';
import { sourceRanges, rangeLabel, exclusionPrompt } from './sourceRanges';
import './review.css';
type Settings = {
  subtitle_style?: import('./editorModel').Style | null;
  aspect_ratio: Ratio;
  visual_mode: 'podcast' | 'mix';
  subtitle_mode: 'sentence' | 'word';
  subtitle_animation: 'none' | 'soft_zoom';
  instansi_ids: string[];
  include_global: boolean;
  mix_hashtags: string[];
  mix_max_per_minute: number | null;
};
export type Proposal = {
  id: string;
  project_id: string;
  revision: number;
  title: string;
  summary: string;
  reason: string;
  start: number;
  end: number;
  original_start: number;
  original_end: number;
  fulfills_prompt: boolean;
  configured: boolean;
  settings: Partial<Settings>;
  instansi_ids: string[];
  status: string;
  job_id: string | null;
  clip_id: string | null;
};
const pending = (p: Proposal) =>
  [
    'queued',
    'running',
    'cancelling',
    'waiting_quota',
    'waiting_service',
    'waiting_network',
  ].includes(p.status);
const tc = (f: number) => {
  const ms = Math.round((f / 30) * 1000);
  return (
    [Math.floor(ms / 3600000), Math.floor(ms / 60000) % 60, Math.floor(ms / 1000) % 60]
      .map((n) => String(n).padStart(2, '0'))
      .join(':') +
    '.' +
    String(ms % 1000).padStart(3, '0')
  );
};
const parse = (s: string) => {
  const parts = s.trim().split(':').map(Number);
  return parts.length <= 3 && parts.every(Number.isFinite)
    ? Math.round(parts.reduce((a, v) => a * 60 + v, 0) * 30)
    : NaN;
};
const yt = (url: string, frame: number) => {
  const u = new URL(url);
  if (u.hostname === 'youtu.be')
    return (
      'https://www.youtube.com/watch?v=' +
      u.pathname.slice(1) +
      '&t=' +
      Math.floor(frame / 30) +
      's'
    );
  u.searchParams.delete('start');
  u.searchParams.set('t', Math.floor(frame / 30) + 's');
  return u.toString();
};
export function Transcript({
  projectId,
  start,
  end,
}: {
  projectId: string;
  start: number;
  end: number;
}) {
  const [rows, setRows] = useState<{ start: number; end: number; text: string }[]>([]),
    [offset, setOffset] = useState(0),
    [shownOffset, setShownOffset] = useState(0),
    [total, setTotal] = useState(0),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    generation = useRef(0);
  useEffect(() => {
    setOffset(0);
  }, [start, end]);
  useEffect(() => {
    const g = ++generation.current;
    setLoading(true);
    setError('');
    const t = setTimeout(() => {
      void api<{ groups: typeof rows; total: number; offset: number }>(
        '/projects/' +
          projectId +
          '/transcript-range?start=' +
          start +
          '&end=' +
          end +
          '&offset=' +
          offset +
          '&limit=30',
      )
        .then((r) => {
          if (g === generation.current) {
            setRows(r.groups);
            setTotal(r.total);
            setShownOffset(r.offset);
          }
        })
        .catch((e) => {
          if (g === generation.current) setError(e.message);
        })
        .finally(() => {
          if (g === generation.current) setLoading(false);
        });
    }, 250);
    return () => {
      clearTimeout(t);
      generation.current++;
    };
  }, [projectId, start, end, offset]);
  return (
    <section className="review-transcript" aria-label="Transkrip bagian sumber">
      {loading ? (
        <p role="status">Memuat transkrip…</p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <>
          {rows.map((r, i) => (
            <p key={i}>
              <time>{stamp(r.start)}</time>
              <span>{r.text}</span>
            </p>
          ))}
          {!rows.length && <p>Belum ada ucapan pada rentang ini.</p>}
          <div className="review-pages">
            <Button
              variant="secondary"
              disabled={!shownOffset}
              onClick={() => {
                setOffset(Math.max(0, shownOffset - 30));
              }}
            >
              Sebelumnya
            </Button>
            <span>
              {total ? shownOffset + 1 : 0}–{Math.min(shownOffset + 30, total)} / {total} kelompok
            </span>
            <Button
              variant="secondary"
              disabled={shownOffset + 30 >= total}
              onClick={() => {
                setOffset(shownOffset + 30);
              }}
            >
              Berikutnya
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
export function ReviewHighlights({
  project,
  clips,
  jobs,
  refresh,
  view = 'transcription',
  detailId,
}: {
  view?: 'transcription' | 'video';
  detailId?: string;
  project: Project;
  clips: Clip[];
  jobs: Job[];
  refresh: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const confirm = useConfirm(),
    [rows, setRows] = useState<Proposal[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [mode, setMode] = useState<'batch' | null>(null);
  const readySelection = useBulkSelection(clips.map((c) => c.id));
  const [renaming, setRenaming] = useState<Clip | null>(null),
    [renameText, setRenameText] = useState(''),
    [ranges, setRanges] = useState<Clip | null>(null);
  const selection = useBulkSelection(rows.filter((p) => p.status !== 'ready').map((p) => p.id));
  async function reload() {
    const r = await api<Proposal[]>('/projects/' + project.id + '/proposals');
    setRows(r);
    await refresh();
  }
  useEffect(() => {
    let live = true;
    const run = () =>
      api<Proposal[]>('/projects/' + project.id + '/proposals')
        .then((r) => {
          if (live) setRows(r);
        })
        .catch((e) => {
          if (live) setError(e.message);
        })
        .finally(() => {
          if (live) setLoading(false);
        });
    void run();
    const t = setInterval(run, 2500);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [project.id]);
  async function close() {
    if (busy) return;
    setMode(null);
  }
  function open(_kind: 'setup', p?: Proposal) {
    if (p) navigate('/transcriptions/' + project.id + '/highlights/' + p.id + '/prepare');
  }
  async function act(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');

    try {
      await fn();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const selected = rows.filter((p) => selection.selected.has(p.id)),
    canBatch =
      selected.length > 0 &&
      selected.every(
        (p) =>
          p.configured &&
          !pending(p) &&
          p.status !== 'ready' &&
          p.start >= 0 &&
          p.end <= Math.floor(project.duration * 30) &&
          p.end - p.start >= 300 &&
          p.end - p.start <= 36000,
      );
  const active = jobs.some(isPending);

  return (
    <main className="mg-page review-page">
      {detailId ? (
        loading ? (
          <p role="status">Memuat detail highlight…</p>
        ) : rows.find((p) => p.id === detailId) ? (
          <ProposalDetail
            key={detailId}
            project={project}
            proposal={rows.find((p) => p.id === detailId)!}
            rows={rows}
            clips={clips}
            refresh={reload}
            onSetup={() =>
              open(
                'setup',
                rows.find((p) => p.id === detailId)!,
              )
            }
          />
        ) : (
          <p role="alert">Usulan tidak ditemukan pada proyek ini.</p>
        )
      ) : (
        <>
          <header className="mg-page-header review-project-header">
            <div>
              <h1>{project.title}</h1>
              <p>
                {rows.filter((p) => !pending(p) && p.status !== 'ready').length} menunggu
                persetujuan · {rows.filter((p) => pending(p)).length} diproses · {clips.length} siap
                diedit
              </p>
            </div>
            <div className="page-header-actions">
              <Link
                className="button secondary"
                to={(view === 'transcription' ? '/projects/' : '/transcriptions/') + project.id}
              >
                {view === 'transcription' ? 'Proyek Video' : 'Proyek Transkripsi'}
              </Link>
              <ProposalSearch project={project} onComplete={() => void reload()} />
              {view === 'transcription' && (
                <SelectionToggle active={selection.selecting} onToggle={selection.toggleMode} />
              )}
            </div>
          </header>
          {error && (
            <p className="notice" role="alert">
              <AlertCircle size={17} />
              {error}
            </p>
          )}
          <RouterRecoveryList jobs={jobs} onComplete={reload} />
          {view === 'transcription' && rows.some((p) => p.status === 'ready') && (
            <details className="panel">
              <summary>Riwayat usulan yang sudah menjadi video</summary>
              {rows
                .filter((p) => p.status === 'ready')
                .map((p) => (
                  <p key={p.id}>
                    {p.title} · {tc(p.start)}–{tc(p.end)}{' '}
                    <Link to={'/projects/' + project.id}>Lihat video</Link>
                  </p>
                ))}
            </details>
          )}
          {jobs.filter(isPending).map((j) => (
            <section className="panel review-job" key={j.id}>
              <div>
                <strong>{kindLabel(j.kind)}</strong>
                <span>{jobLabel(j)}</span>
                <Button
                  variant="secondary"
                  disabled={busy || j.status === 'cancelling'}
                  onClick={() =>
                    void act(async () => {
                      await api('/jobs/' + j.id + '/cancel', 'POST');
                    })
                  }
                >
                  Batalkan
                </Button>
              </div>
              <progress max={100} value={j.progress} />
              <WaitingDetails
                job={j}
                disabled={busy}
                onCheck={() =>
                  void act(async () => {
                    await api('/jobs/' + j.id + '/check', 'POST');
                  })
                }
              />
            </section>
          ))}
          {selection.selecting && (
            <div className="bulk-bar">
              <label>
                <SelectCheckbox
                  label="Pilih semua usulan"
                  checked={rows
                    .filter((p) => !pending(p) && p.status !== 'ready')
                    .every((p) => selection.selected.has(p.id))}
                  onChange={() =>
                    selection.togglePage(
                      rows.filter((p) => !pending(p) && p.status !== 'ready').map((p) => p.id),
                    )
                  }
                />
                Pilih semua usulan
              </label>
              <span>{selected.length} terpilih</span>
              <Button
                disabled={!canBatch || busy}
                onClick={() => {
                  setMode('batch');
                }}
              >
                <Play size={16} />
                Proses terpilih
              </Button>
              <Button
                variant="secondary"
                disabled={!selected.length || selected.some((p) => pending(p)) || busy}
                onClick={() =>
                  void act(async () => {
                    if (
                      !(await confirm({
                        title: 'Hapus usulan terpilih?',
                        description: 'Video sumber dan highlight siap edit tetap tersedia.',
                        danger: true,
                        confirmLabel: 'Hapus',
                      }))
                    )
                      return;
                    for (const p of selected) await api('/proposals/' + p.id, 'DELETE');
                    selection.clear();
                  })
                }
              >
                <Trash2 size={16} />
                Hapus
              </Button>
              {!canBatch && selected.length > 0 && (
                <small>
                  Siapkan konfigurasi setiap usulan dan pastikan durasinya 10 detik–20 menit.
                </small>
              )}
            </div>
          )}
          {loading ? (
            <p role="status">
              <Loader2 className="spin" size={18} />
              Memuat usulan…
            </p>
          ) : view === 'video' && !rows.length && !clips.length ? (
            <div className="mg-empty">
              <FileText size={28} />
              <h2>
                {view === 'video'
                  ? 'Belum ada video siap diedit'
                  : active
                    ? 'Analisis sedang berjalan'
                    : 'Belum ada usulan'}
              </h2>
              <p>
                {view === 'video'
                  ? 'Setujui usulan pada bagian Transkripsi untuk menyiapkan video.'
                  : 'Bagian yang ditemukan akan muncul sebagai usulan untuk kamu tinjau.'}
              </p>
            </div>
          ) : null}
          <HighlightRequestCards
            project={project}
            refresh={reload}
            selecting={selection.selecting}
            selected={selection.selected}
            onSelect={selection.toggle}
            view={view}
          />
          {view === 'video' && clips.length > 0 && (
            <>
              <div className="review-ready-heading">
                <h2 className="review-section-title">Siap diedit</h2>
                <SelectionToggle
                  active={readySelection.selecting}
                  onToggle={readySelection.toggleMode}
                />
              </div>
              {readySelection.selecting && (
                <BulkBar
                  selected={readySelection.selected}
                  visibleIds={clips.map((c) => c.id)}
                  onTogglePage={() => readySelection.togglePage(clips.map((c) => c.id))}
                  onClear={readySelection.clear}
                  disabled={busy || active}
                  onDelete={() =>
                    void act(async () => {
                      if (
                        !(await confirm({
                          title: 'Hapus highlight terpilih?',
                          description: 'Highlight dan hasil ekspor terpilih dihapus permanen.',
                          danger: true,
                          confirmLabel: 'Hapus',
                        }))
                      )
                        return;
                      for (const id of readySelection.selected) await api('/clips/' + id, 'DELETE');
                      readySelection.clear();
                    })
                  }
                />
              )}
              <div className="mg-highlight-grid">
                {clips.map((c) => (
                  <article className="panel review-card" key={c.id}>
                    {readySelection.selecting && (
                      <SelectCheckbox
                        label={'Pilih highlight ' + c.title}
                        checked={readySelection.selected.has(c.id)}
                        disabled={busy || active}
                        onChange={() => readySelection.toggle(c.id)}
                      />
                    )}
                    <h2>{c.title}</h2>
                    <p>{c.reason}</p>
                    <div className="review-range">
                      <span>{c.aspect_ratio}</span>
                      <span>
                        Diambil dari YouTube:{' '}
                        {sourceRanges(c.plan).slice(0, 2).map(rangeLabel).join(' · ')}
                      </span>
                    </div>
                    {sourceRanges(c.plan).length > 2 && (
                      <Button variant="secondary" onClick={() => setRanges(c)}>
                        Lihat semua rentang
                      </Button>
                    )}
                    <footer>
                      <Link
                        className="button primary"
                        to={'/projects/' + project.id + '/clips/' + c.id}
                      >
                        Buka studio
                        <ArrowRight size={16} />
                      </Link>
                      <ActionMenu label={'Aksi ' + c.title}>
                        <ActionItem
                          onClick={() => {
                            setRenaming(c);
                            setRenameText(c.title);
                          }}
                        >
                          <Pencil size={15} />
                          Ubah nama
                        </ActionItem>
                        <ActionItem
                          onClick={() =>
                            void navigator.clipboard
                              .writeText(exclusionPrompt(c.plan))
                              .catch(() => setRanges(c))
                          }
                        >
                          <Copy size={15} />
                          Salin batasan waktu
                        </ActionItem>
                        <ActionItem
                          disabled={busy || active}
                          onClick={() =>
                            void act(async () => {
                              await api('/projects/' + project.id + '/clips', 'POST', {
                                title: (c.title + ' — salinan').slice(0, 200),
                                plan: c.plan,
                                aspect_ratio: c.aspect_ratio,
                                processing_config: c.processing_config,
                                instansi_ids: c.instansi_ids,
                              });
                            })
                          }
                        >
                          <Copy size={15} />
                          Duplikat
                        </ActionItem>
                        <ActionItem
                          danger
                          disabled={busy || active}
                          onClick={() =>
                            void act(async () => {
                              if (
                                await confirm({
                                  title: 'Hapus highlight?',
                                  description: 'Highlight dan hasil ekspornya dihapus permanen.',
                                  confirmLabel: 'Hapus',
                                  danger: true,
                                })
                              )
                                await api('/clips/' + c.id, 'DELETE');
                            })
                          }
                        >
                          <Trash2 size={15} />
                          Hapus highlight
                        </ActionItem>
                      </ActionMenu>
                    </footer>
                  </article>
                ))}
              </div>
            </>
          )}
        </>
      )}
      <Dialog
        open={!!renaming}
        onClose={() => setRenaming(null)}
        title="Ubah nama highlight"
        footer={
          <Button
            disabled={busy || !renameText.trim()}
            onClick={() =>
              void act(async () => {
                if (renaming) {
                  await api('/clips/' + renaming.id, 'PATCH', {
                    title: renameText.trim(),
                    plan: renaming.plan,
                    revision: renaming.revision,
                  });
                  setRenaming(null);
                }
              })
            }
          >
            Simpan nama
          </Button>
        }
      >
        <label>
          Nama highlight
          <input
            value={renameText}
            onChange={(e) => setRenameText(e.target.value)}
            maxLength={200}
          />
        </label>
      </Dialog>
      <Dialog open={!!ranges} onClose={() => setRanges(null)} title="Rentang sumber YouTube">
        {ranges && (
          <div className="mg-dialog-form review-dialog-content">
            <ul>
              {sourceRanges(ranges.plan).map((r, i) => (
                <li key={i}>{rangeLabel(r)}</li>
              ))}
            </ul>
            <label>
              Batasan untuk prompt
              <textarea
                readOnly
                value={exclusionPrompt(ranges.plan)}
                onFocus={(e) => e.target.select()}
              />
            </label>
          </div>
        )}
      </Dialog>
      <Dialog
        open={mode === 'batch'}
        onClose={() => void close()}
        title="Proses highlight terpilih"
        description="Setiap highlight masuk sebagai satu pekerjaan."
        footer={
          <>
            <Button variant="secondary" disabled={busy} onClick={() => setMode(null)}>
              Batal
            </Button>
            <Button
              disabled={busy || !canBatch}
              onClick={() =>
                void act(async () => {
                  await api('/projects/' + project.id + '/proposals/process', 'POST', {
                    items: selected.map((p) => ({ id: p.id, revision: p.revision })),
                  });
                  selection.clear();
                  setMode(null);
                })
              }
            >
              Proses video
            </Button>
          </>
        }
      >
        <ul>
          {selected.map((p) => (
            <li key={p.id}>
              {p.title} · {tc(p.start)}–{tc(p.end)} · {p.settings.aspect_ratio}
            </li>
          ))}
        </ul>
      </Dialog>
    </main>
  );
}
