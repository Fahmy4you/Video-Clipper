import { Camera, Zap, Volume2 } from 'lucide-react';
import type { Transition } from './editorModel';
export function TransitionControls({
  title,
  value,
  onChange,
  begin,
  commit,
}: {
  title: string;
  value: Transition;
  onChange: (patch: Partial<Transition>) => void;
  begin: () => void;
  commit: () => void;
}) {
  return (
    <fieldset className="transition-controls">
      <legend>{title}</legend>
      <label>
        <span>
          <Zap size={14} />
          Animasi
        </span>
        <select
          aria-label={'Animasi ' + title.toLowerCase()}
          value={value.kind}
          onChange={(e) =>
            onChange({
              kind: e.target.value as Transition['kind'],
              ...(e.target.value === 'flash' ? { frames: 12 } : {}),
            })
          }
        >
          <option value="none">Tanpa transisi</option>
          <option value="black">Pudar hitam</option>
          <option value="crossfade">Crossfade</option>
          <option value="flash">Kilatan</option>
        </select>
      </label>
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
              onPointerDown={begin}
              onPointerUp={commit}
              onPointerCancel={commit}
              onChange={(e) => onChange({ frames: +e.target.value })}
            />
            <output>{(value.frames / 30).toFixed(2)} s</output>
          </div>
        </label>
      )}
      <label>
        <span>
          <Camera size={14} />
          Sound effect
        </span>
        <select
          aria-label={'Sound effect ' + title.toLowerCase()}
          value={value.sound || 'none'}
          onChange={(e) => onChange({ sound: e.target.value as Transition['sound'] })}
        >
          <option value="none">Tidak ada</option>
          <option value="camera_shutter">Camera shutter</option>
        </select>
      </label>
      {value.sound === 'camera_shutter' && (
        <label>
          <span>
            <Volume2 size={14} />
            Volume sound effect
          </span>
          <div className="range-field">
            <input
              aria-label={'Volume sound effect ' + title.toLowerCase()}
              type="range"
              min={0}
              max={100}
              value={Math.round((value.sound_volume ?? 1) * 100)}
              onPointerDown={begin}
              onPointerUp={commit}
              onPointerCancel={commit}
              onChange={(e) => onChange({ sound_volume: +e.target.value / 100 })}
            />
            <output>{Math.round((value.sound_volume ?? 1) * 100)}%</output>
          </div>
          <small>Titik tengah suara tepat pada perpindahan.</small>
        </label>
      )}
    </fieldset>
  );
}
