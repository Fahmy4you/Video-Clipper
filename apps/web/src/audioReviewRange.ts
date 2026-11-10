export function initialAudioArea(total: number, start: number, end: number): [number, number] {
  const length = Math.min(
    total,
    Math.min(36000, Math.max(18000, end - start > 18000 ? end - start + 900 : 18000)),
  );
  const left = Math.round(Math.max(0, Math.min(total - length, (start + end - length) / 2)));
  return [left, left + length];
}
