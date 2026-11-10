import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, ZoomIn, ZoomOut, ChevronLeft, ChevronRight } from 'lucide-react';
import { Dialog, useConfirm } from './components/Ui';
import {
  TimeRangeFields,
  partsFromFrame,
  frameFromParts,
  validRange,
  frameLabel,
  type TimeParts,
} from './components/TimeRangeFields';
import { api } from './api';
import type { Proposal } from './ReviewHighlights';
import { durationLabel, mixCapacity } from './timeRange';
import { peaks, type AudioState } from './reviewAudioData';
import { useReviewPlayer } from './useReviewPlayer';
import { initialAudioArea } from './audioReviewRange';

const empty = (): TimeParts => ({ h: '00', m: '00', s: '' });
export function AudioRevision({
  projectId,
  proposal,
  duration,
  state,
  onClose,
  refresh,
  onDirty,
}: {
  projectId: string;
  proposal: Proposal;
  duration: number;
  state: AudioState;
  onClose: () => void;
  refresh: () => Promise<void>;
  onDirty: (dirty: boolean) => void;
}) {
  const total = Math.floor(duration * 30),
    confirm = useConfirm();
  const [base] = useState(proposal),
    [initial] = useState(() => initialAudioArea(total, proposal.start, proposal.end));
  const [area, setArea] = useState<[number, number]>(initial),
    [view, setView] = useState<[number, number]>(initial);
  const [areaStart, setAreaStart] = useState(partsFromFrame(initial[0])),
    [areaEnd, setAreaEnd] = useState(partsFromFrame(initial[1]));
  const [start, setStart] = useState(partsFromFrame(base.start)),
    [end, setEnd] = useState(partsFromFrame(base.end));
  const [cleared, setCleared] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [waveError, setWaveError] = useState(''),
    [waveRetry, setWaveRetry] = useState(0);
  const [wave, setWave] = useState<Awaited<ReturnType<typeof peaks>> | null>(null);
  const [mode, setMode] = useState<'area' | 'selection'>('area');
  const player = useReviewPlayer(state.audio_url, area[0], area[1]);
  const a = frameFromParts(start),
    b = frameFromParts(end),
    aa = frameFromParts(areaStart),
    bb = frameFromParts(areaEnd);
  const valid = validRange(start, end, duration) && a >= area[0] && b <= area[1];
  const areaValid = validRange(areaStart, areaEnd, duration);
  const dirty = !cleared && (a !== base.start || b !== base.end);
  const track = useRef<HTMLDivElement>(null),
    gesture = useRef<{
      edge: 'start' | 'end' | 'create';
      frame: number;
      x: number;
      moved: boolean;
    } | null>(null),
    closing = useRef(false);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  useEffect(() => {
    const old = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    return () => {
      document.documentElement.style.overflow = old;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setWave(null);
    setWaveError('');
    if (state.waveform_status === 'ready')
      void peaks(
        '/api/projects/' +
          projectId +
          '/review-audio/waveform?start=' +
          view[0] +
          '&end=' +
          view[1] +
          '&points=2048&v=' +
          state.version,
        controller.signal,
      )
        .then((value) => {
          if (!controller.signal.aborted) setWave(value);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setWaveError(e.message);
        });
    return () => controller.abort();
  }, [projectId, state.waveform_status, state.version, view[0], view[1], waveRetry]);
  useEffect(() => {
    player.pause();
  }, [a, b]);
  async function close() {
    if (busy || closing.current) return;
    closing.current = true;
    player.pause();
    if (
      !dirty ||
      (await confirm({
        title: 'Buang revisi audio?',
        description: 'Pilihan highlight belum disimpan.',
        confirmLabel: 'Buang perubahan',
      }))
    )
      onClose();
    closing.current = false;
  }
  function show() {
    if (!areaValid) return;
    player.pause();
    const next: [number, number] = [aa, bb];
    setArea(next);
    setView(next);
    if (!valid || a < aa || b > bb) {
      setStart(empty());
      setEnd(empty());
      setCleared(true);
    }
  }
  function select(first: number, last: number) {
    player.pause();
    setCleared(false);
    setStart(partsFromFrame(first));
    setEnd(partsFromFrame(last));
  }
  function constrainView(left: number, length: number) {
    length = Math.max(
      Math.min(300, area[1] - area[0]),
      Math.min(area[1] - area[0], Math.round(length)),
    );
    left = Math.round(Math.max(area[0], Math.min(area[1] - length, left)));
    setView([left, left + length]);
  }
  function zoom(factor: number) {
    const length = (view[1] - view[0]) * factor;
    constrainView((view[0] + view[1] - length) / 2, length);
  }
  const pct = (frame: number) => (100 * (frame - view[0])) / (view[1] - view[0]);
  function at(x: number) {
    const rect = track.current!.getBoundingClientRect();
    return Math.round(
      view[0] + Math.max(0, Math.min(1, (x - rect.left) / rect.width)) * (view[1] - view[0]),
    );
  }
  function move(x: number) {
    const g = gesture.current;
    if (!g) return;
    const frame = at(x);
    if (Math.abs(x - g.x) > 3) g.moved = true;
    if (g.edge === 'create') {
      if (g.moved) select(Math.min(g.frame, frame), Math.max(g.frame, frame));
    } else if (g.edge === 'start')
      select(Math.max(area[0], b - 36000, Math.min(b - 300, frame)), b);
    else select(a, Math.min(area[1], a + 36000, Math.max(a + 300, frame)));
  }
  function begin(e: React.PointerEvent<HTMLElement>, edge: 'start' | 'end' | 'create') {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    player.pause();
    gesture.current = { edge, frame: at(e.clientX), x: e.clientX, moved: false };
  }
  function finish(e: React.PointerEvent<HTMLElement>) {
    e.stopPropagation();
    const g = gesture.current;
    if (g?.edge === 'create' && !g.moved) player.seek(at(e.clientX) / 30);
    gesture.current = null;
  }
  const path = useMemo(() => {
    let result = '';
    if (wave)
      for (let i = 0; i < wave.values.length; i += 2) {
        const x =
          (1000 * ((wave.start + (i / 2) * wave.step) * 30 - view[0])) / (view[1] - view[0]);
        result +=
          'M' +
          x.toFixed(2) +
          ',' +
          (50 - (wave.values[i] / 32768) * 45).toFixed(2) +
          'V' +
          (50 - (wave.values[i + 1] / 32768) * 45).toFixed(2);
      }
    return result;
  }, [wave, view[0], view[1]]);
  const adjusted =
    valid &&
    !!base.settings.mix_max_per_minute &&
    base.settings.mix_max_per_minute > mixCapacity(b - a);
  async function save() {
    if (!valid || busy) return;
    setBusy(true);
    setError('');
    player.pause();
    try {
      await api('/proposals/' + base.id, 'PATCH', {
        revision: base.revision,
        title: base.title,
        summary: base.summary,
        start: a,
        end: b,
        ...(adjusted
          ? {
              settings: {
                ...base.settings,
                instansi_ids: base.instansi_ids,
                mix_max_per_minute: mixCapacity(b - a),
              },
            }
          : {}),
      });
      onDirty(false);
      await refresh();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open
      title="Revisi bagian melalui audio"
      className="audio-revision-dialog"
      description="Atur area dengar, lalu pilih bagian yang ingin dijadikan highlight."
      onClose={() => void close()}
      footer={
        <>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => void close()}
          >
            Batal
          </button>
          <button
            type="button"
            className="button primary"
            disabled={!valid || busy}
            onClick={() => void save()}
          >
            {busy ? 'Menyimpan…' : 'Simpan revisi'}
          </button>
        </>
      }
    >
      <div className="audio-revision-content">
        <audio ref={player.audio} src={state.audio_url!} preload="metadata" {...player.events} />
        <fieldset className="audio-revision-fields">
          <legend>Area dengar</legend>
          <TimeRangeFields
            compact
            start={areaStart}
            end={areaEnd}
            duration={duration}
            onStart={(v) => {
              player.pause();
              setAreaStart(v);
            }}
            onEnd={(v) => {
              player.pause();
              setAreaEnd(v);
            }}
          />
          <div className="audio-revision-row">
            <span>10 detik–20 menit</span>
            <button
              type="button"
              className="button secondary"
              disabled={!areaValid || busy}
              onClick={show}
            >
              Tampilkan
            </button>
          </div>
        </fieldset>
        <div>
          <div
            className="review-wave"
            ref={track}
            role="group"
            aria-label="Waveform area dengar"
            onPointerDown={(e) => begin(e, 'create')}
            onPointerMove={(e) => move(e.clientX)}
            onPointerUp={finish}
            onPointerCancel={() => {
              gesture.current = null;
            }}
          >
            <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
              <path d={path} />
            </svg>
            {valid && (
              <div
                className="review-selection"
                style={{
                  left: Math.max(0, pct(a)) + '%',
                  width: Math.max(0, Math.min(100, pct(b)) - Math.max(0, pct(a))) + '%',
                }}
              />
            )}
            {valid && (
              <>
                <div
                  className="review-outside-selection"
                  style={{ left: 0, width: Math.max(0, Math.min(100, pct(a))) + '%' }}
                />
                <div
                  className="review-outside-selection"
                  style={{ right: 0, width: Math.max(0, Math.min(100, 100 - pct(b))) + '%' }}
                />
              </>
            )}
            <i
              className="review-playhead"
              style={{ left: Math.max(0, Math.min(100, pct(player.position * 30))) + '%' }}
            />
            {valid &&
              (['start', 'end'] as const).map((edge) => {
                const frame = edge === 'start' ? a : b;
                return (
                  pct(frame) >= 0 &&
                  pct(frame) <= 100 && (
                    <button
                      key={edge}
                      type="button"
                      role="slider"
                      className="review-handle"
                      aria-label={
                        edge === 'start' ? 'Batas awal highlight' : 'Batas akhir highlight'
                      }
                      aria-valuenow={frame}
                      aria-valuetext={frameLabel(frame, duration)}
                      aria-valuemin={edge === 'start' ? Math.max(area[0], b - 36000) : a + 300}
                      aria-valuemax={edge === 'start' ? b - 300 : Math.min(area[1], a + 36000)}
                      style={{ left: 'clamp(22px, ' + pct(frame) + '%, calc(100% - 22px))' }}
                      disabled={busy}
                      onPointerDown={(e) => begin(e, edge)}
                      onPointerMove={(e) => {
                        e.stopPropagation();
                        move(e.clientX);
                      }}
                      onPointerUp={finish}
                      onKeyDown={(e) => {
                        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                          e.preventDefault();
                          const f =
                            frame + (e.key === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 30 : 1);
                          if (edge === 'start')
                            select(Math.max(area[0], b - 36000, Math.min(b - 300, f)), b);
                          else select(a, Math.min(area[1], a + 36000, Math.max(a + 300, f)));
                        }
                      }}
                    />
                  )
                );
              })}
            {!wave && (
              <span className="review-wave-status">{waveError || 'Menyiapkan waveform…'}</span>
            )}
          </div>
          <div className="review-wave-labels">
            <span>{frameLabel(view[0], duration)}</span>
            <span>{frameLabel(view[1], duration)}</span>
          </div>
          <div className="review-audio-controls">
            <button
              type="button"
              className="button secondary"
              title="Zoom masuk"
              aria-label="Zoom masuk"
              onClick={() => zoom(0.5)}
            >
              <ZoomIn size={18} />
            </button>
            <button
              type="button"
              className="button secondary"
              title="Zoom keluar"
              aria-label="Zoom keluar"
              onClick={() => zoom(2)}
            >
              <ZoomOut size={18} />
            </button>
            <button
              type="button"
              className="button secondary"
              title="Geser tampilan ke kiri"
              aria-label="Geser tampilan ke kiri"
              onClick={() => constrainView(view[0] - (view[1] - view[0]) / 2, view[1] - view[0])}
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              className="button secondary"
              title="Geser tampilan ke kanan"
              aria-label="Geser tampilan ke kanan"
              onClick={() => constrainView(view[0] + (view[1] - view[0]) / 2, view[1] - view[0])}
            >
              <ChevronRight size={18} />
            </button>
          </div>
          {waveError && (
            <button
              type="button"
              className="button secondary"
              onClick={() => setWaveRetry((v) => v + 1)}
            >
              Coba lagi waveform
            </button>
          )}
        </div>
        <fieldset className="audio-revision-fields">
          <legend>Pilihan highlight</legend>
          {cleared && <p role="status">Tentukan pilihan highlight di area ini</p>}
          <TimeRangeFields
            compact
            start={start}
            end={end}
            duration={duration}
            onStart={(v) => {
              player.pause();
              setCleared(false);
              setStart(v);
            }}
            onEnd={(v) => {
              player.pause();
              setCleared(false);
              setEnd(v);
            }}
          />
          {Number.isFinite(a + b) && <p>Durasi pilihan: {durationLabel(Math.max(0, b - a))}</p>}
          {!valid && !cleared && (
            <p role="alert">
              Pilihan harus berada dalam area dengar dan berdurasi 10 detik–20 menit.
            </p>
          )}
          {adjusted && (
            <p role="status">
              Batas sisipan akan disesuaikan menjadi {mixCapacity(b - a)} per menit sesuai durasi
              baru.
            </p>
          )}
        </fieldset>
        <div className="review-audio-controls">
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              if (player.playing && mode === 'area') player.pause();
              else {
                setMode('area');
                void player.play(area[0] / 30, area[1] / 30);
              }
            }}
          >
            {player.playing && mode === 'area' ? <Pause size={18} /> : <Play size={18} />}{' '}
            {player.playing && mode === 'area' ? 'Jeda area' : 'Putar area'}
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={!valid}
            onClick={() => {
              if (player.playing && mode === 'selection') player.pause();
              else {
                setMode('selection');
                void player.play(a / 30, b / 30);
              }
            }}
          >
            {player.playing && mode === 'selection' ? <Pause size={18} /> : <Play size={18} />}{' '}
            {player.playing && mode === 'selection' ? 'Jeda pilihan' : 'Putar pilihan'}
          </button>
          <span>{frameLabel(Math.round(player.position * 30), duration)}</span>
        </div>
        {player.loading && <p role="status">Memuat audio…</p>}
        {(error || player.error) && (
          <p role="alert">
            {error || player.error}{' '}
            {player.error && (
              <button
                type="button"
                className="button secondary"
                onClick={() => player.audio.current?.load()}
              >
                Coba lagi
              </button>
            )}
          </p>
        )}
      </div>
    </Dialog>
  );
}
