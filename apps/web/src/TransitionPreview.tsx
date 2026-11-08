import { useContext, useEffect, useRef, useState } from 'react';
import type { Transition } from './editorModel';
import { PreviewEnabled, usePreviewScope } from './SubtitleSettings';
import { flashField } from './transitionEffects';
import { transitionWeights } from './boundaries';

const choices = [
  ['none', 'Tanpa transisi'],
  ['black', 'Pudar hitam'],
  ['crossfade', 'Crossfade'],
  ['flash', 'Kilatan'],
] as const;
let images: Promise<HTMLImageElement[]> | undefined;
function loadImages() {
  return (images ??= Promise.all(
    ['window', 'garden'].map(
      (name) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve(image);
          image.onerror = reject;
          image.src = '/transition-demo/cat-' + name + '.png';
        }),
    ),
  ).catch((error) => {
    images = undefined;
    throw error;
  }));
}
export function TransitionPreview({
  group,
  value,
  reverse,
  onChange,
}: {
  group: string;
  value: Transition;
  reverse: boolean;
  onChange: (p: Partial<Transition>) => void;
}) {
  return (
    <div className="subtitle-grid">
      {choices.map(([kind, label]) => (
        <TransitionCard
          key={kind}
          id={group + ':' + kind}
          label={label}
          kind={kind}
          checked={value.kind === kind}
          frames={kind === 'flash' && value.kind !== 'flash' ? 12 : value.frames}
          reverse={reverse}
          select={() =>
            onChange({ kind, ...(kind === 'flash' && value.kind !== kind ? { frames: 12 } : {}) })
          }
        />
      ))}
    </div>
  );
}
function TransitionCard({
  id,
  label,
  kind,
  checked,
  frames,
  reverse,
  select,
}: {
  id: string;
  label: string;
  kind: Transition['kind'];
  checked: boolean;
  frames: number;
  reverse: boolean;
  select: () => void;
}) {
  const scope = usePreviewScope(),
    enabled = useContext(PreviewEnabled);
  const card = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false),
    [reduced, setReduced] = useState(false),
    [manual, setManual] = useState(false);
  const [error, setError] = useState(false),
    [retry, setRetry] = useState(0);
  const active =
    enabled && visible && (scope.hover || scope.selected) === id && (!reduced || manual);
  useEffect(() => {
    const observer = new IntersectionObserver(([e]) => setVisible(e.isIntersecting));
    observer.observe(card.current!);
    const q = matchMedia('(prefers-reduced-motion: reduce)'),
      change = () => setReduced(q.matches);
    change();
    q.addEventListener('change', change);
    return () => {
      observer.disconnect();
      q.removeEventListener('change', change);
    };
  }, []);
  useEffect(() => {
    let live = true,
      raf = 0,
      start = 0;
    const duration = Math.max(0, frames / 30);
    const field = document.createElement('canvas');
    field.width = 96;
    field.height = 64;
    let pictures: HTMLImageElement[] = [];
    function draw(seconds: number) {
      const ctx = canvas.current?.getContext('2d');
      if (!ctx || !pictures.length) return;
      const phase = duration
        ? Math.max(0, Math.min(1, (seconds - 0.8) / duration))
        : Number(seconds >= 0.8);
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, 540, 300);
      const weights = transitionWeights(kind, phase);
      const ordered = reverse ? [...pictures].reverse() : pictures;
      ctx.globalCompositeOperation = 'lighter';
      ordered.forEach((image, index) => {
        const scale = Math.max(540 / image.width, 300 / image.height);
        ctx.globalAlpha = weights[index];
        ctx.drawImage(
          image,
          (540 - image.width * scale) / 2,
          (300 - image.height * scale) * 0.25,
          image.width * scale,
          image.height * scale,
        );
      });
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
      if (kind === 'flash' && phase > 0 && phase < 1) {
        field.getContext('2d')!.putImageData(new ImageData(flashField(phase), 96, 64), 0, 0);
        ctx.drawImage(field, 0, 0, 540, 300);
      }
    }
    function tick(now: number) {
      if (!live) return;
      if (!start) start = now;
      draw(((now - start) / 1000) % (1.6 + duration));
      if (active && !document.hidden) raf = requestAnimationFrame(tick);
    }
    function resume() {
      cancelAnimationFrame(raf);
      start = 0;
      if (active && !document.hidden) raf = requestAnimationFrame(tick);
      else draw(0.8 + duration * 0.75);
    }
    loadImages()
      .then((p) => {
        if (live) {
          pictures = p;
          setError(false);
          resume();
        }
      })
      .catch(() => {
        if (live) setError(true);
      });
    document.addEventListener('visibilitychange', resume);
    return () => {
      live = false;
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', resume);
    };
  }, [active, kind, frames, reverse, retry]);
  return (
    <div
      ref={card}
      className={'subtitle-card transition-card ' + (checked ? 'selected' : '')}
      onPointerEnter={(e) => {
        if (e.pointerType === 'mouse') scope.setHover(id);
      }}
      onPointerLeave={() => scope.setHover(null)}
      onFocus={() => scope.setHover(id)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) scope.setHover(null);
      }}
    >
      <label>
        <input
          type="radio"
          name={id.split(':')[0]}
          checked={checked}
          onChange={() => {
            select();
            scope.setSelected(id);
            scope.setHover(null);
          }}
        />
        <span>{label}</span>
        <canvas ref={canvas} width={540} height={300} aria-hidden="true" />
      </label>
      {error && (
        <button type="button" onClick={() => setRetry(retry + 1)}>
          Coba lagi memuat gambar
        </button>
      )}
      {reduced && (
        <button
          type="button"
          className="button secondary"
          onClick={() => {
            scope.setSelected(id);
            setManual(!manual);
          }}
        >
          {manual ? 'Hentikan contoh' : 'Putar contoh'}
        </button>
      )}
    </div>
  );
}
