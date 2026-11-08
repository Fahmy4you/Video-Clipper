export type TimeParts = { h: string; m: string; s: string };
export const partsFromFrame = (frame: number): TimeParts => ({
  h: String(Math.floor(frame / 108000)).padStart(2, '0'),
  m: String(Math.floor(frame / 1800) % 60).padStart(2, '0'),
  s: (Math.round(((frame % 1800) / 30) * 1000) / 1000).toFixed(frame % 30 ? 3 : 0).padStart(2, '0'),
});
export function frameFromParts(parts: TimeParts) {
  if (!/^\d+$/.test(parts.h) || !/^\d+$/.test(parts.m) || !/^\d+(\.\d{1,3})?$/.test(parts.s))
    return NaN;
  const h = Number(parts.h),
    m = Number(parts.m),
    s = Number(parts.s);
  return m <= 59 && s < 60 ? Math.round((h * 3600 + m * 60 + s) * 30) : NaN;
}
export function frameLabel(frame: number, duration = 3600) {
  const p = partsFromFrame(frame);
  return [duration >= 3600 ? p.h : null, duration >= 60 ? p.m : null, p.s]
    .filter((x) => x !== null)
    .join(':');
}
export function validRange(start: TimeParts, end: TimeParts, duration: number) {
  const a = frameFromParts(start),
    b = frameFromParts(end);
  return (
    Number.isFinite(a + b) &&
    a >= 0 &&
    b - a >= 300 &&
    b - a <= 36000 &&
    b <= Math.floor(duration * 30)
  );
}

export function durationLabel(frames: number) {
  const ms = Math.round((frames / 30) * 1000);
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor(ms / 60000) % 60;
  const seconds = (ms % 60000) / 1000;
  return [
    hours ? hours + ' jam' : '',
    minutes ? minutes + ' menit' : '',
    seconds || (!hours && !minutes)
      ? seconds.toLocaleString('id-ID', { maximumFractionDigits: 3 }) + ' detik'
      : '',
  ]
    .filter(Boolean)
    .join(' ');
}
export function mixCapacity(frames: number) {
  return Math.max(0, Math.min(5, Math.floor(Math.floor((frames * 3) / 10) / 90)));
}

/** Compact elapsed/audio duration; source timecodes use frameLabel separately. */
export function compactDuration(value: number) {
  if (!Number.isFinite(value)) return '—';
  const total = Math.max(0, Math.floor(value));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total / 60) % 60;
  const seconds = total % 60;
  return [hours ? hours + 'j' : '', hours || minutes ? minutes + 'm' : '', seconds + 'd']
    .filter(Boolean)
    .join(' ');
}
