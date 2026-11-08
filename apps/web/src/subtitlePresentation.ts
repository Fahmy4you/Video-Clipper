import type { Caption, Style } from './editorModel';
// Mirrored with backend/app/subtitle_presentation.py; all timing uses integer frames.
export function subtitlePresentation(c: Caption, s: Style, frame: number) {
  let words = c.words,
    start = c.start,
    end = c.end;
  if (s.subtitle_mode === 'word') {
    const word = words.find((w) => w.start <= frame && frame < w.end);
    if (!word) return { words: [], scale: 1 };
    words = [word];
    start = word.start;
    end = word.end;
  }
  let scale = 1;
  if (s.subtitle_animation === 'soft_zoom') {
    const phase = Math.min(4, Math.floor((end - start - 1) / 2));
    if (phase > 0) {
      const x = frame - start,
        remaining = end - 1 - frame;
      if (x < phase) scale = 0.9 + 0.1 * (1 - (1 - x / phase) ** 3);
      else if (remaining < phase) scale = 0.96 + 0.04 * (1 - (1 - remaining / phase) ** 3);
    }
  }
  return { words, scale };
}
