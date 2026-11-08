import type { Plan } from './editorModel';
export function sourceRanges(plan: Plan) {
  const sorted = plan.segments
      .map((s) => ({ start: s.source_in, end: s.source_in + s.duration }))
      .sort((a, b) => a.start - b.start),
    out: { start: number; end: number }[] = [];
  for (const range of sorted) {
    const last = out.at(-1);
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else out.push({ ...range });
  }
  return out;
}
export function sourceStamp(seconds: number) {
  const s = Math.max(0, seconds),
    h = Math.floor(s / 3600),
    m = Math.floor(s / 60) % 60;
  return (
    (h ? String(h).padStart(2, '0') + ':' : '') +
    String(m).padStart(2, '0') +
    ':' +
    String(s % 60).padStart(2, '0')
  );
}
export function rangeLabel(r: { start: number; end: number }) {
  return sourceStamp(Math.floor(r.start / 30)) + '–' + sourceStamp(Math.ceil(r.end / 30));
}
export function exclusionPrompt(plan: Plan) {
  return (
    'Jangan ambil bagian ' +
    sourceRanges(plan).map(rangeLabel).join(' dan ') +
    ' dari video sumber.'
  );
}
