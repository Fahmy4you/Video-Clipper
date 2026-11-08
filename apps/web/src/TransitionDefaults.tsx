import { useContext, useEffect, useRef, useState } from 'react';
import { Camera, VolumeX } from 'lucide-react';
import type { Transition } from './editorModel';
import { TransitionPreview } from './TransitionPreview';
import { PreviewEnabled } from './SubtitleSettings';
import { catalog, getBuffer, getContext } from './TransitionAudio';
export type TransitionDefaultsValue = { same: boolean; incoming: Transition; outgoing: Transition };
export const defaultTransitions = (): TransitionDefaultsValue => ({
  same: true,
  incoming: { kind: 'black', frames: 9, sound: 'none', sound_volume: 1 },
  outgoing: { kind: 'black', frames: 9, sound: 'none', sound_volume: 1 },
});
let stopAudition = () => {};
export function TransitionDefaults({
  value,
  onChange,
}: {
  value: TransitionDefaultsValue;
  onChange: (v: TransitionDefaultsValue) => void;
}) {
  const enabled = useContext(PreviewEnabled);
  useEffect(() => {
    if (!enabled) stopAudition();
    const hidden = () => {
      if (document.hidden) stopAudition();
    };
    document.addEventListener('visibilitychange', hidden);
    return () => {
      stopAudition();
      document.removeEventListener('visibilitychange', hidden);
    };
  }, [enabled]);
  function update(key: 'incoming' | 'outgoing', patch: Partial<Transition>) {
    const next = { ...value, [key]: { ...value[key], ...patch } };
    if (value.same) next.outgoing = { ...next.incoming };
    onChange(next);
  }
  return (
    <div className="prepare-transitions">
      <label className="source-global-toggle">
        <input
          type="checkbox"
          checked={value.same}
          onChange={(e) => {
            stopAudition();
            onChange({
              ...value,
              same: e.target.checked,
              ...(e.target.checked ? { outgoing: { ...value.incoming } } : {}),
            });
          }}
        />
        Samakan transisi masuk dan keluar
      </label>
      <TransitionGroup
        title={value.same ? 'Transisi masuk & keluar' : 'Transisi masuk'}
        group="incoming"
        reverse={false}
        value={value.incoming}
        onChange={(p) => update('incoming', p)}
      />
      {!value.same && (
        <TransitionGroup
          title="Transisi keluar"
          group="outgoing"
          reverse
          value={value.outgoing}
          onChange={(p) => update('outgoing', p)}
        />
      )}
    </div>
  );
}
function TransitionGroup({
  title,
  group,
  reverse,
  value,
  onChange,
}: {
  title: string;
  group: string;
  reverse: boolean;
  value: Transition;
  onChange: (p: Partial<Transition>) => void;
}) {
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
      stopAudition();
    },
    [],
  );
  async function audition() {
    stopAudition();
    const token = ++generation.current;
    let source: AudioBufferSourceNode | undefined, gain: GainNode | undefined;
    stopAudition = () => {
      generation.current++;
      try {
        source?.stop();
      } catch {}
      source?.disconnect();
      gain?.disconnect();
    };
    try {
      const ctx = getContext();
      await ctx.resume();
      const effects = await catalog(),
        effect = effects.find((e) => e.id === 'camera_shutter');
      if (!effect) throw Error('Camera shutter tidak tersedia.');
      const buffer = await getBuffer(ctx, effect.audio_url);
      if (token !== generation.current) return;
      setError('');
      source = ctx.createBufferSource();
      gain = ctx.createGain();
      source.buffer = buffer;
      gain.gain.value = value.sound_volume ?? 1;
      source.connect(gain);
      gain.connect(ctx.destination);
      source.onended = () => {
        source?.disconnect();
        gain?.disconnect();
      };
      source.start();
    } catch (e) {
      if (token === generation.current) setError((e as Error).message);
    }
  }
  return (
    <fieldset className="prepare-transition-group">
      <legend>{title}</legend>
      <TransitionPreview group={group} value={value} reverse={reverse} onChange={onChange} />
      <div
        className="prepare-sounds"
        role="group"
        aria-label={'Sound effect ' + title.toLowerCase()}
      >
        <button
          type="button"
          className="button secondary"
          aria-pressed={!value.sound || value.sound === 'none'}
          onClick={() => {
            stopAudition();
            setError('');
            onChange({ sound: 'none' });
          }}
        >
          <VolumeX size={18} />
          Tidak ada
        </button>
        <button
          type="button"
          className="button secondary"
          aria-pressed={value.sound === 'camera_shutter'}
          onClick={() => {
            onChange({ sound: 'camera_shutter' });
            void audition();
          }}
        >
          <Camera size={18} />
          Camera shutter
        </button>
      </div>
      {error && (
        <p role="alert">
          {error}{' '}
          <button type="button" className="button secondary" onClick={() => void audition()}>
            Coba lagi
          </button>
        </p>
      )}
      <div className="prepare-fields">
        {value.kind !== 'none' && (
          <label>
            Durasi animasi
            <div className="range-field">
              <input
                aria-label={'Durasi ' + title.toLowerCase()}
                type="range"
                min={0}
                max={30}
                value={value.frames}
                onChange={(e) => onChange({ frames: +e.target.value })}
              />
              <output>{(value.frames / 30).toFixed(2)} detik</output>
            </div>
          </label>
        )}
        {value.sound === 'camera_shutter' && (
          <label>
            Volume sound effect
            <div className="range-field">
              <input
                aria-label={'Volume ' + title.toLowerCase()}
                type="range"
                min={0}
                max={100}
                value={Math.round((value.sound_volume ?? 1) * 100)}
                onChange={(e) => {
                  stopAudition();
                  onChange({ sound_volume: +e.target.value / 100 });
                }}
              />
              <output>{Math.round((value.sound_volume ?? 1) * 100)}%</output>
            </div>
          </label>
        )}
      </div>
    </fieldset>
  );
}
