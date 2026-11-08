import { useEffect, useRef, useState } from 'react';
import { Link, useBlocker, useNavigate, useParams } from 'react-router-dom';
import { Save, Play, RotateCcw, ArrowLeft, LoaderCircle } from 'lucide-react';
import { api, type Project } from './api';
import type { Proposal } from './ReviewHighlights';
import { formats, type Style, type VideoAsset } from './editorModel';
import { TagSelect, useConfirm } from './components/Ui';
import type { Instansi } from './components/SourceOwnership';
import { durationLabel, mixCapacity } from './timeRange';
import { frameLabel } from './components/TimeRangeFields';
import { PreviewScope, SubtitleSettings } from './SubtitleSettings';
import { modernStyle, templates, motions } from './subtitleTemplates';
import {
  TransitionDefaults,
  defaultTransitions,
  type TransitionDefaultsValue,
} from './TransitionDefaults';
import { PrepareAccordion } from './PrepareAccordion';
import './video-prepare.css';
type Settings = {
  aspect_ratio: Project['aspect_ratio'];
  visual_mode: 'podcast' | 'mix';
  subtitle_mode: 'sentence' | 'word';
  subtitle_animation: 'none' | 'soft_zoom';
  subtitle_style: Style | null;
  transition_defaults: TransitionDefaultsValue;
  instansi_ids: string[];
  include_global: boolean;
  mix_hashtags: string[];
  mix_max_per_minute: number | null;
};
const defaults = (): Settings => ({
  aspect_ratio: '9:16',
  visual_mode: 'podcast',
  subtitle_mode: 'sentence',
  subtitle_animation: 'none',
  subtitle_style: modernStyle(),
  transition_defaults: defaultTransitions(),
  instansi_ids: [],
  include_global: true,
  mix_hashtags: [],
  mix_max_per_minute: null,
});
export function VideoPrepare() {
  const { id, proposalId } = useParams(),
    navigate = useNavigate(),
    confirm = useConfirm();
  const [proposal, setProposal] = useState<Proposal | null>(null),
    [project, setProject] = useState<Project | null>(null);
  const [settings, setSettings] = useState<Settings>(defaults),
    [initial, setInitial] = useState('');
  const [assets, setAssets] = useState<VideoAsset[]>([]),
    [owners, setOwners] = useState<Instansi[]>([]);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const leaving = useRef(false);
  const back = '/transcriptions/' + id + '/highlights/' + proposalId;
  const dirty = !!initial && JSON.stringify(settings) !== initial;
  const blocker = useBlocker(() => dirty && !leaving.current);
  useEffect(() => {
    if (blocker.state === 'blocked')
      void confirm({
        title: 'Buang perubahan belum tersimpan?',
        description: 'Pengaturan belum disimpan.',
        confirmLabel: 'Buang perubahan',
      }).then((ok) => (ok ? blocker.proceed() : blocker.reset()));
  }, [blocker.state]);
  useEffect(() => {
    const fn = (e: BeforeUnloadEvent) => {
      if (dirty && !leaving.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', fn);
    return () => window.removeEventListener('beforeunload', fn);
  }, [dirty]);
  useEffect(() => {
    let live = true;
    Promise.all([
      api<Proposal>('/proposals/' + proposalId),
      api<Project>('/projects/' + id),
      api<{ style: Partial<Settings> }>('/video-preferences'),
      api<VideoAsset[]>('/video-clips'),
      api<Instansi[]>('/instansi'),
    ])
      .then(([p, pr, prefs, v, o]) => {
        if (!live) return;
        if (p.project_id !== id) throw Error('Usulan tidak ditemukan pada proyek ini.');
        const st = {
          ...defaults(),
          ...(p.configured ? p.settings : prefs.style),
          instansi_ids: p.instansi_ids,
        };
        if (p.configured && !p.settings.subtitle_style) st.subtitle_style = null;
        if (st.mix_max_per_minute !== null)
          st.mix_max_per_minute = Math.min(st.mix_max_per_minute, mixCapacity(p.end - p.start));
        setProposal(p);
        setProject(pr);
        setSettings(st);
        setInitial(JSON.stringify(st));
        setAssets(v);
        setOwners(o);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [id, proposalId]);
  async function save(process: boolean) {
    if (!proposal || busy) return;
    setBusy(true);
    setError('');
    try {
      const p =
        proposal.configured && !dirty
          ? proposal
          : await api<Proposal>('/proposals/' + proposal.id, 'PATCH', {
              title: proposal.title,
              summary: proposal.summary,
              start: proposal.start,
              end: proposal.end,
              revision: proposal.revision,
              settings,
            });
      setProposal(p);
      setInitial(JSON.stringify(settings));
      if (process) {
        await api('/projects/' + id + '/proposals/process', 'POST', {
          items: [{ id: p.id, revision: p.revision }],
          remember_style: true,
        });
        leaving.current = true;
        navigate(back);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const a = proposal?.start || 0,
    b = proposal?.end || 0;
  const allowed = assets.filter(
    (v) =>
      v.status === 'ready' &&
      !v.archived &&
      v.frames >= 90 &&
      (!v.scenes.length || v.scenes.some((s) => s.end - s.start >= 90)) &&
      ((v.scope === 'global' && (!settings.instansi_ids.length || settings.include_global)) ||
        (v.scope === 'instansi' && v.instansi_ids.some((i) => settings.instansi_ids.includes(i)))),
  );
  const tags = [...new Set(allowed.flatMap((v) => v.hashtags))];
  const options = [...new Set([...tags, ...settings.mix_hashtags])].sort().map((t) => ({
    id: t,
    label: t + (tags.includes(t) ? '' : ' — tidak tersedia untuk sumber ini'),
  }));
  const sourceSummary = !settings.instansi_ids.length
    ? 'Global saja'
    : settings.instansi_ids.map((i) => owners.find((o) => o.id === i)?.name || i).join(', ') +
      (settings.include_global ? ' + Global' : '');
  const locked = proposal && !['review', 'failed', 'cancelled'].includes(proposal.status);
  if (!proposal || !project)
    return (
      <main className="video-prepare">
        <p role={error ? 'alert' : 'status'}>{error || 'Memuat pengaturan…'}</p>
      </main>
    );
  const style = settings.subtitle_style;
  return (
    <main className="video-prepare">
      <header>
        <Link className="prepare-back" to={back}>
          <ArrowLeft size={16} />
          Kembali ke detail highlight
        </Link>
        <h1>Siapkan video</h1>
        <div className="prepare-heading">
          <div className="prepare-highlight">
            <h2>{proposal.title}</h2>
            <p>
              {frameLabel(a, project.duration)}–{frameLabel(b, project.duration)} ·{' '}
              {durationLabel(b - a)}
            </p>
          </div>
          {!locked && (
            <div className="prepare-actions">
              <button
                type="button"
                className="button secondary"
                aria-label="Kembalikan ke bawaan aplikasi"
                title="Kembalikan ke bawaan aplikasi"
                disabled={busy}
                onClick={() =>
                  setSettings({
                    ...settings,
                    subtitle_style: modernStyle(),
                    transition_defaults: defaultTransitions(),
                  })
                }
              >
                <RotateCcw size={16} />
              </button>
              <button
                className="button secondary"
                aria-label="Simpan pengaturan"
                title="Simpan pengaturan"
                disabled={busy}
                onClick={() => void save(false)}
              >
                <Save size={16} />
              </button>
              <button
                className="button primary"
                aria-label="Proses video"
                title="Proses video"
                disabled={busy}
                onClick={() => void save(true)}
              >
                {busy ? <LoaderCircle className="spin" size={18} /> : <Play size={18} />}
              </button>
            </div>
          )}
        </div>
        <span className="sr-only" role="status">
          {busy ? 'Menyimpan dan menyiapkan permintaan…' : ''}
        </span>
      </header>
      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      {locked ? (
        <p className="notice">
          Pengaturan terkunci selama pemrosesan atau setelah video siap.{' '}
          <Link to={back}>Lihat status highlight</Link>
        </p>
      ) : (
        <PreviewScope>
          <section className="panel prepare-section">
            <h2>Pengaturan utama</h2>
            <div className="mg-dialog-form review-dialog-content">
              <label>
                Tampilan video
                <select
                  aria-label="Tampilan video"
                  value={settings.visual_mode}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      visual_mode: e.target.value as Settings['visual_mode'],
                    })
                  }
                >
                  <option value="podcast">Podcast saja</option>
                  <option value="mix">Mix</option>
                </select>
              </label>
              {settings.visual_mode === 'mix' && (
                <>
                  <TagSelect
                    prefix=""
                    noun="instansi"
                    max={100}
                    label="Instansi sumber · opsional"
                    options={owners.map((i) => ({ id: i.id, label: i.name }))}
                    value={settings.instansi_ids}
                    onChange={(ids) =>
                      setSettings({
                        ...settings,
                        instansi_ids: ids,
                        include_global:
                          !settings.instansi_ids.length || !ids.length
                            ? true
                            : settings.include_global,
                      })
                    }
                  />
                  {settings.instansi_ids.length > 0 && (
                    <label className="source-global-toggle">
                      <input
                        type="checkbox"
                        checked={settings.include_global}
                        onChange={(e) =>
                          setSettings({ ...settings, include_global: e.target.checked })
                        }
                      />
                      Sertakan video Global
                    </label>
                  )}
                  <p className="field-help">Sumber: {sourceSummary}</p>
                </>
              )}
              <fieldset className="ratio-options">
                <legend>Rasio video</legend>
                {formats.map((f) => (
                  <button
                    type="button"
                    key={f.id}
                    aria-pressed={settings.aspect_ratio === f.id}
                    className={settings.aspect_ratio === f.id ? 'active' : ''}
                    onClick={() => setSettings({ ...settings, aspect_ratio: f.id })}
                  >
                    <span className="ratio-icon">
                      <i style={{ aspectRatio: f.width + '/' + f.height, width: 24 }} />
                    </span>
                    <strong>{f.id}</strong>
                    <small>{f.label}</small>
                  </button>
                ))}
              </fieldset>
              {settings.visual_mode === 'mix' && (
                <>
                  <div className="mix-density">
                    {mixCapacity(b - a) <= 1 ? (
                      <p>
                        Maksimal 1 sisipan, hingga{' '}
                        {durationLabel(Math.min(150, Math.floor((b - a) * 0.3)))}.
                      </p>
                    ) : (
                      <>
                        <label className="source-global-toggle">
                          <input
                            type="checkbox"
                            checked={settings.mix_max_per_minute !== null}
                            onChange={(e) =>
                              setSettings({
                                ...settings,
                                mix_max_per_minute: e.target.checked ? mixCapacity(b - a) : null,
                              })
                            }
                          />
                          Batasi jumlah sisipan per menit
                        </label>
                        {settings.mix_max_per_minute !== null && (
                          <label>
                            Maksimal sisipan per menit
                            <select
                              aria-label="Maksimal sisipan per menit"
                              value={settings.mix_max_per_minute}
                              onChange={(e) =>
                                setSettings({
                                  ...settings,
                                  mix_max_per_minute: Number(e.target.value),
                                })
                              }
                            >
                              {Array.from({ length: mixCapacity(b - a) }, (_, i) => (
                                <option key={i + 1} value={i + 1}>
                                  {i + 1}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                      </>
                    )}
                    <ul className="mix-help">
                      <li>Jumlah sisipan mengikuti relevansi; batas bukan jumlah wajib.</li>
                      <li>Jika batasnya 5 tetapi hanya 3 yang relevan, gunakan 3 sisipan.</li>
                      <li>Setiap sisipan berdurasi 3–5 detik.</li>
                      <li>Porsi maksimal 30% setiap menit, termasuk sisa menit.</li>
                      <li>Sisipan boleh tidak digunakan jika tidak ada adegan yang sesuai.</li>
                    </ul>
                  </div>
                  <TagSelect
                    label="Batasi topik sisipan — opsional"
                    options={options}
                    value={settings.mix_hashtags}
                    onChange={(v) => setSettings({ ...settings, mix_hashtags: v })}
                  />
                  <p className="field-help">
                    {
                      allowed.filter((v) =>
                        settings.mix_hashtags.every((t) => v.hashtags.includes(t)),
                      ).length
                    }{' '}
                    video siap digunakan. Semua hashtag terpilih wajib dimiliki kandidat.
                  </p>
                  {!allowed.some((v) =>
                    settings.mix_hashtags.every((t) => v.hashtags.includes(t)),
                  ) && (
                    <p className="notice">
                      Tidak ada sisipan yang sesuai. Video tetap diproses dengan tampilan podcast.
                    </p>
                  )}
                </>
              )}
            </div>
          </section>
          <PrepareAccordion
            title="Subtitle — opsional"
            summary={
              style?.subtitle_version === 1
                ? (templates.find((t) => t[0] === style.subtitle_template)?.[1] ||
                    'Default kalimat') +
                  ' · ' +
                  (motions.find((m) => m[0] === style.subtitle_motion)?.[1] || 'Tanpa animasi')
                : 'Gaya lama'
            }
          >
            <SubtitleSettings
              value={
                style || {
                  ...modernStyle(),
                  subtitle_version: undefined,
                  subtitle_mode: settings.subtitle_mode,
                  subtitle_animation: settings.subtitle_animation,
                  karaoke: true,
                }
              }
              onChange={(v) => setSettings({ ...settings, subtitle_style: v })}
            />
          </PrepareAccordion>
          <PrepareAccordion
            title="Transisi sisipan — opsional"
            disabled={settings.visual_mode !== 'mix'}
            summary={
              settings.visual_mode !== 'mix'
                ? 'Aktifkan Mix untuk mengatur transisi sisipan.'
                : settings.transition_defaults.same
                  ? 'Masuk dan keluar sama'
                  : 'Masuk dan keluar berbeda'
            }
          >
            <TransitionDefaults
              value={settings.transition_defaults}
              onChange={(v) => setSettings({ ...settings, transition_defaults: v })}
            />
          </PrepareAccordion>
          <p className="field-help">
            Gaya subtitle dan transisi akan diingat setelah Proses video diterima. Semua pengaturan
            dapat diedit lagi di studio; rasio terkunci setelah diproses.
          </p>
        </PreviewScope>
      )}
    </main>
  );
}
