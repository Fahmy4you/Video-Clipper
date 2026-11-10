import type { Style, Caption } from './editorModel';

export const templates = [
  ['sentence', 'Default kalimat'],
  ['word', 'Default per kata'],
  ['background', 'Sorotan latar'],
  ['reveal', 'Muncul bertahap — Turun'],
  ['reveal_up', 'Muncul bertahap — Naik'],
  ['karaoke', 'Karaoke bertahan'],
  ['karaoke_active', 'Sorot kata aktif'],
] as const;
export const motions = [
  ['none', 'Tanpa animasi'],
  ['fade', 'Pudar'],
  ['zoom', 'Zoom'],
  ['zoom_fade', 'Zoom + Pudar'],
  ['down', 'Turun'],
  ['down_fade', 'Turun + Pudar'],
] as const;
export function modernStyle(): Style {
  return {
    x: 0.5,
    y: 0.84,
    width: 0.88,
    height: 0.2,
    rotation: 0,
    opacity: 1,
    font: 'DejaVu Sans',
    size: 62,
    color: '#FFFFFF',
    highlight: '#5EEAD4',
    background: '#FACC15',
    outline: 3,
    align: 'center',
    karaoke: false,
    subtitle_version: 1,
    subtitle_template: 'sentence',
    subtitle_motion: 'none',
  };
}
export const ease = (value: number) => {
  const x = Math.max(0, Math.min(1, value));
  return x * x * x * (x * (x * 6 - 15) + 10);
};
type Box = {
  x: number;
  y: number;
  width: number;
  text: string;
  word: Caption['words'][number];
  row: number;
  ascent: number;
  descent: number;
};
const layouts = new WeakMap<CanvasRenderingContext2D, Map<string, Box[]>>();

export function readableAt(start: number, end: number, frame: number, exit = true) {
  const phase = Math.min(3, Math.floor((end - start) / 3));
  if (!phase) return 1;
  const entering = 0.7 + 0.3 * ease((frame - start) / phase);
  const leaving = exit ? ease((end - 1 - frame) / phase) : 1;
  return Math.min(entering, leaving);
}

export function motionAt(start: number, end: number, frame: number, motion: string) {
  const phase = Math.min(9, Math.floor((end - start) / 3));
  const entering = phase ? ease((frame - start) / phase) : 1;
  const leaving = phase ? ease((end - 1 - frame) / phase) : 1;
  const gain = Math.min(entering, leaving);
  return {
    opacity: motion.includes('fade') ? readableAt(start, end, frame) : 1,
    scale: motion.includes('zoom') ? 0.96 + 0.04 * gain : 1,
    dy: motion.includes('down') ? 0.12 * (leaving < 1 ? 1 - leaving : entering - 1) : 0,
  };
}
export function drawSubtitle(
  ctx: CanvasRenderingContext2D,
  caption: Caption,
  style: Style,
  frame: number,
  w: number,
  h: number,
) {
  const mode = style.subtitle_template || 'sentence';
  const active = caption.words.findIndex((x) => x.start <= frame && frame < x.end);
  if (mode === 'word' && active < 0) return;
  const words = mode === 'word' ? [caption.words[active]] : caption.words;
  const unit = mode === 'word' ? words[0] : caption;
  const group = motionAt(unit.start, unit.end, frame, style.subtitle_motion || 'none');
  const size = Math.max(1, Math.round((style.size * w) / 1080));
  ctx.save();
  ctx.translate(style.x * w, style.y * h + group.dy * size);
  ctx.rotate((style.rotation * Math.PI) / 180);
  ctx.scale(group.scale, group.scale);
  ctx.font = `600 ${size}px "${style.font}"`;
  ctx.textBaseline = 'alphabetic';
  ctx.lineJoin = 'round';
  let cache = layouts.get(ctx);
  if (!cache) {
    cache = new Map();
    layouts.set(ctx, cache);
  }
  const key = JSON.stringify([words, style.font, size, style.width * w, style.align]);
  const fontsReady = ctx.canvas.ownerDocument?.fonts.check(ctx.font) ?? true;
  let boxes = fontsReady ? cache.get(key) : undefined;
  if (!boxes) {
    const metrics = ctx.measureText('ÁÉHgyp'),
      ascent = metrics.actualBoundingBoxAscent,
      descent = metrics.actualBoundingBoxDescent,
      space = ctx.measureText(' ').width,
      limit = style.width * w;
    const lines: { text: string; width: number; word: (typeof words)[number] }[][] = [[]];
    let width = 0;
    for (const word of words) {
      word.text.split('\n').forEach((text, j) => {
        if (j) {
          lines.push([]);
          width = 0;
        }
        const tw = ctx.measureText(text).width;
        if (lines.at(-1)!.length && width + space + tw > limit) {
          lines.push([]);
          width = 0;
        }
        if (lines.at(-1)!.length) width += space;
        lines.at(-1)!.push({ text, width: tw, word });
        width += tw;
      });
    }
    boxes = [];
    lines.forEach((line, row) => {
      const tw = line.reduce((n, t) => n + t.width, 0) + space * Math.max(0, line.length - 1);
      let x =
        style.align === 'center' ? -tw / 2 : style.align === 'left' ? -limit / 2 : limit / 2 - tw;
      const y = (-lines.length * size * 1.25) / 2 + row * size * 1.25 + size * 0.1;
      line.forEach((t) => {
        boxes!.push({ ...t, x, y: y + ascent, row, ascent, descent });
        x += t.width + space;
      });
    });
    if (cache.size >= 32) cache.delete(cache.keys().next().value!);
    if (fontsReady) cache.set(key, boxes);
  }
  ctx.globalAlpha = style.opacity * group.opacity;
  if (mode === 'background' && active >= 0) {
    const target = boxes.find((b) => b.word.id === caption.words[active]?.id);
    const previous = boxes.find((b) => b.word.id === caption.words[active - 1]?.id);
    if (target) {
      const duration = target.word.end - target.word.start;
      const phase = duration < 3 ? 0 : Math.min(3, duration - 1);
      const t = phase
        ? 1 - (1 - Math.max(0, Math.min(1, (frame - target.word.start) / phase))) ** 3
        : 1;
      const same =
        previous && previous.row === target.row && previous.word.end === target.word.start;
      const x = same ? previous.x + (target.x - previous.x) * t : target.x;
      const width = same ? previous.width + (target.width - previous.width) * t : target.width;
      ctx.save();
      if (previous && previous.row !== target.row) ctx.globalAlpha *= t;
      ctx.fillStyle = style.background || '#FACC15';
      ctx.beginPath();
      ctx.roundRect(
        x - size * 0.12,
        target.y - target.ascent - size * 0.08,
        width + size * 0.24,
        target.ascent + target.descent + size * 0.16,
        size * 0.15,
      );
      ctx.fill();
      ctx.restore();
    }
  }
  for (const box of boxes) {
    if ((mode === 'reveal' || mode === 'reveal_up') && frame < box.word.start) continue;
    const phase = Math.max(0, Math.min(9, box.word.end - box.word.start - 1));
    const t =
      (mode === 'reveal' || mode === 'reveal_up') && phase
        ? ease((frame - box.word.start) / phase)
        : 1;
    ctx.save();
    const wordOpacity =
      mode === 'reveal' || mode === 'reveal_up'
        ? readableAt(box.word.start, box.word.end, frame, false)
        : 1;
    ctx.globalAlpha = style.opacity * Math.min(group.opacity, wordOpacity);
    const y = box.y + (mode === 'reveal_up' ? 1 : -1) * (1 - t) * size * 0.12;
    ctx.lineWidth = ((style.outline * w) / 1080) * 2;
    ctx.strokeStyle = '#101010';
    if (style.outline) ctx.strokeText(box.text, box.x, y);
    ctx.fillStyle =
      (mode === 'karaoke' && frame >= box.word.start) ||
      (mode === 'karaoke_active' && box.word.id === caption.words[active]?.id)
        ? style.highlight
        : style.color;
    ctx.fillText(box.text, box.x, y);
    ctx.restore();
  }
  ctx.restore();
}
