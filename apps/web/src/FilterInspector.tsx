import type { TimelineFilter, FilterTarget } from './editorModel';
export function FilterInspector({
  item,
  overlapping,
  duration,
  change,
  begin,
  commit,
}: {
  item: TimelineFilter;
  overlapping: boolean;
  duration: number;
  change: (patch: Partial<TimelineFilter>) => void;
  begin: () => void;
  commit: () => void;
}) {
  return (
    <>
      <p>Tajam</p>
      <p className="muted">
        Mempertegas detail pada rentang highlight. Tidak menambah resolusi sumber.
      </p>
      <label>
        Kekuatan
        <div className="filter-strength">
          <input
            aria-label="Kekuatan filter"
            type="range"
            min={0}
            max={100}
            value={item.strength}
            onPointerDown={begin}
            onPointerUp={commit}
            onPointerCancel={commit}
            onChange={(e) => change({ strength: +e.target.value })}
          />
          <input
            aria-label="Kekuatan filter persen"
            type="number"
            min={0}
            max={100}
            value={item.strength}
            onChange={(e) =>
              change({ strength: Math.max(0, Math.min(100, Math.round(+e.target.value))) })
            }
          />
          <span>%</span>
        </div>
      </label>
      <div className="inspector-grid">
        <label>
          Mulai filter (detik)
          <input
            aria-label="Mulai filter"
            type="number"
            step={1 / 30}
            min={0}
            max={(item.end - 1) / 30}
            value={item.start / 30}
            onChange={(e) =>
              change({
                start: Math.max(0, Math.min(item.end - 1, Math.round(+e.target.value * 30))),
              })
            }
          />
        </label>
        <label>
          Akhir filter (detik)
          <input
            aria-label="Akhir filter"
            type="number"
            step={1 / 30}
            min={(item.start + 1) / 30}
            max={duration / 30}
            value={item.end / 30}
            onChange={(e) =>
              change({
                end: Math.max(item.start + 1, Math.min(duration, Math.round(+e.target.value * 30))),
              })
            }
          />
        </label>
      </div>
      <p className="field-help">
        Durasi {((item.end - item.start) / 30).toFixed(2)} detik · mengikuti waktu highlight.
      </p>
      <fieldset className="filter-targets">
        <legend>Terapkan pada</legend>
        {(
          [
            ['image', 'Gambar'],
            ['podcast', 'Video Podcast'],
            ['broll', 'Video Sisipan'],
          ] as [FilterTarget, string][]
        ).map(([target, label]) => (
          <label key={target}>
            <input
              type="checkbox"
              checked={item.targets.includes(target)}
              onChange={(e) =>
                change({
                  targets: e.target.checked
                    ? [...item.targets, target]
                    : item.targets.filter((t) => t !== target),
                })
              }
            />
            {label}
          </label>
        ))}
      </fieldset>
      {(!item.strength || !item.targets.length) && (
        <p className="broll-notice">Tidak memberi efek.</p>
      )}
      {overlapping && (
        <p className="broll-notice">
          Saat filter bertumpuk, kekuatan tertinggi digunakan untuk setiap target.
        </p>
      )}
    </>
  );
}
