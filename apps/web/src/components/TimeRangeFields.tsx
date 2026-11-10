import { useId } from 'react';
import './timeRange.css';

import {
  partsFromFrame,
  frameFromParts,
  frameLabel,
  validRange,
  durationLabel,
  type TimeParts,
} from '../timeRange';
export {
  partsFromFrame,
  frameFromParts,
  frameLabel,
  validRange,
  type TimeParts,
} from '../timeRange';
export function TimeRangeFields({
  start,
  end,
  duration,
  onStart,
  onEnd,
  compact = false,
}: {
  compact?: boolean;
  start: TimeParts;
  end: TimeParts;
  duration: number;
  onStart: (value: TimeParts) => void;
  onEnd: (value: TimeParts) => void;
}) {
  const id = useId(),
    maximum = Math.floor(duration * 30);
  const fields: { key: keyof TimeParts; name: string; short: string }[] = [
    ...(duration >= 3600 ? [{ key: 'h' as const, name: 'Jam', short: 'J' }] : []),
    ...(duration >= 60 ? [{ key: 'm' as const, name: 'Menit', short: 'M' }] : []),
    { key: 's', name: 'Detik', short: 'D' },
  ];
  const a = frameFromParts(start),
    b = frameFromParts(end);
  const valid = validRange(start, end, duration);
  return (
    <div className="time-range-control">
      <div className="time-range-groups">
        {[
          { label: 'Waktu mulai', value: start, change: onStart },
          { label: 'Waktu akhir', value: end, change: onEnd },
        ].map((group, index) => {
          const frame = frameFromParts(group.value);
          const error = !Number.isFinite(frame)
            ? 'Jam dan menit harus bilangan bulat; menit 00–59 dan detik 0–kurang dari 60. Tidak boleh negatif.'
            : frame > maximum
              ? 'Waktu melewati durasi video sumber.'
              : '';
          return (
            <fieldset key={group.label}>
              <legend>{group.label}</legend>
              <div className="time-part-fields">
                {fields.map((field) => (
                  <label key={field.key}>
                    <span className="sr-only">
                      {group.label} — {field.name}
                    </span>
                    <input
                      aria-label={group.label + ' — ' + field.name}
                      type="text"
                      inputMode={field.key === 's' ? 'decimal' : 'numeric'}
                      value={group.value[field.key]}
                      aria-invalid={!!error}
                      aria-describedby={id + '-error-' + index}
                      onChange={(e) =>
                        group.change({ ...group.value, [field.key]: e.target.value })
                      }
                    />
                    <span aria-hidden="true">{field.short}</span>
                  </label>
                ))}
              </div>
              <small id={id + '-error-' + index} role={error ? 'alert' : undefined}>
                {error}
              </small>
            </fieldset>
          );
        })}
      </div>
      {!compact && (
        <ul className="time-range-help">
          <li>
            Rentang tersedia: {frameLabel(0, duration)}–{frameLabel(maximum, duration)}
          </li>
          {Number.isFinite(a + b) && (
            <>
              <li>Waktu mulai: {frameLabel(a, duration)}</li>
              <li>Waktu akhir: {frameLabel(b, duration)}</li>
              <li>Durasi pilihan: {durationLabel(Math.max(0, b - a))}</li>
            </>
          )}
          <li>Batas highlight: 10 detik–20 menit</li>
          <li>Menit: 00–59; detik: 0 hingga kurang dari 60</li>
          <li>Ketelitian: 30 fps</li>
        </ul>
      )}
      {!valid && Number.isFinite(a + b) && (
        <p role="alert">
          {b - a > 36000
            ? 'Durasi highlight maksimal 20 menit. Sesuaikan waktu mulai atau akhir.'
            : b - a < 300
              ? 'Durasi highlight minimal 10 detik.'
              : 'Rentang harus berada dalam video sumber.'}
        </p>
      )}
    </div>
  );
}
