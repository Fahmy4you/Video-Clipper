import { useEffect, useState } from 'react';
import { Link, useBlocker } from 'react-router-dom';
import { ArrowLeft, Pencil, Settings2, Save, Play } from 'lucide-react';
import { api, type Project, type Clip } from './api';
import { durationLabel, mixCapacity } from './timeRange';
import { createLucideIcon } from 'lucide-react';

import { Transcript, type Proposal } from './ReviewHighlights';
import { ReviewAudio } from './ReviewAudio';
import { Button } from './components/ui/button';
import { useConfirm } from './components/Ui';
import { frameLabel } from './components/TimeRangeFields';

const Youtube = createLucideIcon('Youtube', [
  ['rect', { x: 2, y: 5, width: 20, height: 14, rx: 4, key: 'body' }],
  ['path', { d: 'm10 9 5 3-5 3Z', key: 'play' }],
]);

function youtubeLink(url: string, frame: number) {
  const parsed = new URL(url);
  if (parsed.hostname === 'youtu.be') {
    return (
      'https://www.youtube.com/watch?v=' +
      parsed.pathname.slice(1) +
      '&t=' +
      Math.floor(frame / 30) +
      's'
    );
  }
  parsed.searchParams.set('t', Math.floor(frame / 30) + 's');
  return parsed.toString();
}
export function ProposalDetail({
  project,
  proposal,
  rows,
  clips,
  refresh,
  onSetup,
}: {
  project: Project;
  proposal: Proposal;
  rows: Proposal[];
  clips: Clip[];
  refresh: () => Promise<void>;
  onSetup: () => void;
}) {
  const p = proposal,
    confirm = useConfirm();
  const [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [title, setTitle] = useState(p.title),
    [summary, setSummary] = useState(p.summary);
  const [audioDirty, setAudioDirty] = useState(false);
  const [base, setBase] = useState(p.revision);
  const a = p.start,
    b = p.end;
  const dirty = audioDirty || (editing && (title !== p.title || summary !== p.summary));
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    void confirm({
      title: 'Buang perubahan belum tersimpan?',
      description: 'Revisi belum disimpan.',
      confirmLabel: 'Buang perubahan',
    }).then((ok) => {
      if (ok) blocker.proceed();
      else blocker.reset();
    });
  }, [blocker.state]);
  useEffect(() => {
    const before = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', before);
    return () => window.removeEventListener('beforeunload', before);
  }, [dirty]);
  const pending = [
    'queued',
    'running',
    'cancelling',
    'waiting_quota',
    'waiting_service',
    'waiting_network',
  ].includes(p.status);
  const changed = p.start !== p.original_start || p.end !== p.original_end;
  const valid = true;
  const overlaps =
    rows.some((x) => x.id !== p.id && x.start < b && x.end > a) ||
    clips.some(
      (c) =>
        c.id !== p.clip_id &&
        c.plan.segments.some((s) => s.source_in < b && s.source_in + s.duration > a),
    );
  return (
    <div className="proposal-detail">
      <Link className="mg-back" to={'/transcriptions/' + project.id}>
        <ArrowLeft size={16} />
        Kembali ke proyek
      </Link>
      <header className="mg-page-header">
        <div>
          <small>Peninjauan usulan highlight</small>
          <h1>{p.title}</h1>
        </div>
        {p.status === 'ready' && p.clip_id ? (
          <Link className="button primary" to={'/projects/' + project.id + '/clips/' + p.clip_id}>
            <Play size={16} />
            Buka studio
          </Link>
        ) : (
          <Button disabled={pending || busy || dirty} onClick={onSetup}>
            <Settings2 size={16} />
            Siapkan video
          </Button>
        )}
      </header>
      <section className="panel proposal-section">
        <div className="proposal-section-header">
          <h2>Informasi highlight</h2>
          {!editing && (
            <Button
              variant="secondary"
              disabled={pending || p.status === 'ready'}
              onClick={() => {
                setTitle(p.title);
                setSummary(p.summary);
                setBase(p.revision);
                setEditing(true);
                setError('');
              }}
            >
              <Pencil size={16} />
              Ubah informasi
            </Button>
          )}
        </div>
        {editing ? (
          <form
            className="mg-dialog-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError('');
              try {
                await api('/proposals/' + p.id, 'PATCH', {
                  revision: base,
                  title: title.trim(),
                  summary,
                  start: a,
                  end: b,
                  ...(p.settings.mix_max_per_minute &&
                  p.settings.mix_max_per_minute > mixCapacity(b - a)
                    ? {
                        settings: {
                          ...p.settings,
                          instansi_ids: p.instansi_ids,
                          mix_max_per_minute: mixCapacity(b - a),
                        },
                      }
                    : {}),
                });
                setEditing(false);
                await refresh();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Judul
              <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              Ringkasan
              <textarea
                value={summary}
                maxLength={2000}
                rows={4}
                onChange={(e) => setSummary(e.target.value)}
              />
            </label>
            <div className="proposal-actions">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={async () => {
                  if (
                    !dirty ||
                    (await confirm({
                      title: 'Buang perubahan?',
                      description: 'Revisi belum disimpan.',
                      confirmLabel: 'Buang',
                    }))
                  )
                    setEditing(false);
                }}
              >
                Batal
              </Button>
              <Button disabled={busy || !valid || !title.trim()}>
                <Save size={16} />
                Simpan revisi
              </Button>
            </div>
          </form>
        ) : (
          <>
            <p className="detail-prose">{p.summary || 'Ringkasan belum tersedia.'}</p>
            <div className="detail-source-time">
              <p className="request-time">
                Waktu sumber: {frameLabel(p.start, project.duration)}–
                {frameLabel(p.end, project.duration)}
              </p>
              <p>Durasi: {durationLabel(p.end - p.start)}</p>
            </div>
          </>
        )}
        {error && (
          <p role="alert" className="notice">
            {error}
          </p>
        )}
        {valid && overlaps && (
          <p className="field-help">
            Sebagian rentang ini pernah digunakan oleh usulan atau highlight lain. Pilihan tetap
            diperbolehkan.
          </p>
        )}
        {valid && (
          <a
            className="button secondary detail-video-link"
            href={youtubeLink(project.url, a)}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Youtube size={16} />
            Buka Video
          </a>
        )}
      </section>
      <ReviewAudio
        projectId={project.id}
        proposal={p}
        duration={project.duration}
        refresh={refresh}
        locked={pending || p.status === 'ready' || editing || busy}
        onDirty={setAudioDirty}
      />
      <section className="panel proposal-section">
        <h2>Alasan dipilih</h2>
        <p className="detail-prose">{p.reason}</p>
        {changed && (
          <p className="field-help">
            Rentang sudah direvisi. Alasan ini mengacu pada usulan awal{' '}
            {frameLabel(p.original_start, project.duration)}–
            {frameLabel(p.original_end, project.duration)}.
          </p>
        )}
      </section>
      <section className="panel proposal-section">
        <h2>Transkrip sumber</h2>
        <p className="field-help">Baca saja · mengikuti rentang pilihan.</p>
        {valid ? (
          <Transcript projectId={project.id} start={p.start} end={p.end} />
        ) : (
          <p>Perbaiki rentang untuk melihat transkrip.</p>
        )}
      </section>
      {p.status !== 'review' && (
        <p className="notice">
          Status penyusunan video: {p.status}.{' '}
          {p.status === 'failed'
            ? 'Usulan tetap tersedia. Buka Siapkan video untuk mencoba pemrosesan kembali.'
            : ''}
        </p>
      )}
    </div>
  );
}
