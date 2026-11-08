import { visualLayers, visualSpans } from './boundaries';
import {
  PreviewMedia,
  type PreviewFrame,
  type PreviewStatus,
  type MediaNeed,
} from './PreviewMedia';
import { Sharpener } from './Sharpener';
import { paintFlash } from './transitionEffects';
import { drawSubtitle } from './subtitleTemplates';
import { subtitlePresentation } from './subtitlePresentation';
import React, { useEffect, useRef, useState } from 'react';
import {
  filterStrength,
  globalBroll,
  fadeGain,
  total,
  brollWeights,
  type AudioAsset,
  type VideoAsset,
  atFrame,
  formats,
  clamp,
  type Plan,
  type Style,
  type Asset,
  type Caption,
  type Overlay,
  type Segment,
} from './editorModel';
export type Selection = {
  kind: 'video' | 'caption' | 'overlay' | 'audio' | 'broll' | 'filter' | 'transition';
  segmentId: string;
  id: string;
};
type Props = {
  audioAssets: AudioAsset[];
  retry: number;
  onStatus: (status: PreviewStatus) => void;
  sourceFrames: number;
  onBuffering: (b: boolean) => void;
  quality: 'light' | 'sharp';
  onQualityReady: () => void;
  onQualityWarning: (text: string) => void;
  videoAssets: VideoAsset[];
  plan: Plan;
  ratio: string;
  frame: number;
  playing: boolean;
  setFrame: (n: number) => void;
  setPlaying: (b: boolean) => void;
  src: string;
  assets: Asset[];
  selection: Selection | null;
  select: (s: Selection) => void;
  changeStyle: (patch: Partial<Style>) => void;
  changeTransform: (patch: Partial<Segment['transform']>) => void;
  begin: () => void;
  commit: () => void;
};
const font = (s: Style, w: number) => `600 ${(s.size * w) / 1080}px "${s.font}"`;
function drawText(
  ctx: CanvasRenderingContext2D,
  item: Caption | Overlay,
  style: Style,
  frame: number,
  w: number,
  h: number,
) {
  if ('words' in item && style.subtitle_version === 1) {
    drawSubtitle(ctx, item, style, frame, w, h);
    return;
  }
  const display = 'words' in item ? subtitlePresentation(item, style, frame) : null;
  if (display && !display.words.length) return;
  ctx.save();
  ctx.globalAlpha = style.opacity;
  ctx.translate(style.x * w, style.y * h);
  ctx.rotate((style.rotation * Math.PI) / 180);
  if (display) ctx.scale(display.scale, display.scale);
  ctx.font = font(style, w);
  ctx.textBaseline = 'top';
  ctx.lineJoin = 'round';
  const size = (style.size * w) / 1080,
    space = ctx.measureText(' ').width,
    limit = style.width * w;
  const tokens =
    'words' in item
      ? display!.words.map((x) => ({
          text: x.text,
          color: style.karaoke && frame >= x.start ? style.highlight : style.color,
        }))
      : item.text.split(' ').map((text) => ({ text, color: style.color }));
  const lines: { text: string; color: string; width: number }[][] = [[]];
  let width = 0;
  for (const token of tokens) {
    token.text.split('\n').forEach((text, j) => {
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
      lines.at(-1)!.push({ text, color: token.color, width: tw });
      width += tw;
    });
  }
  const lh = size * 1.25;
  lines.forEach((line, i) => {
    const tw = line.reduce((n, x) => n + x.width, 0) + space * Math.max(0, line.length - 1);
    let x =
      style.align === 'center' ? -tw / 2 : style.align === 'left' ? -limit / 2 : limit / 2 - tw;
    const y = (-lines.length * lh) / 2 + i * lh + size * 0.1;
    line.forEach((t) => {
      const inkY = y + ctx.measureText(t.text).actualBoundingBoxAscent;
      ctx.lineWidth = ((style.outline * w) / 1080) * 2;
      ctx.strokeStyle = '#101010';
      if (style.outline) ctx.strokeText(t.text, x, inkY);
      ctx.fillStyle = t.color;
      ctx.fillText(t.text, x, inkY);
      x += t.width + space;
    });
  });
  ctx.restore();
}
export function EditorCanvas(props: Props) {
  const stage = useRef<HTMLDivElement>(null),
    container = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    video = useRef<HTMLVideoElement>(null),
    latest = useRef(props),
    images = useRef(new Map<string, HTMLImageElement>()),
    paint = useRef<(force?: boolean) => void>(() => {}),
    [box, setBox] = useState({ width: 1, height: 1 });
  latest.current = props;
  const format = formats.find((f) => f.id === props.ratio) || formats[0],
    media = useRef<PreviewMedia | null>(null),
    chosen = useRef(new Map<string, PreviewFrame>()),
    buffered = useRef(false),
    layers = useRef(new Map<string, HTMLCanvasElement>()),
    sharpeners = useRef(new Map<string, Sharpener>());
  const lastPaint = useRef<{ plan: Plan; selection: Selection | null; key: string } | null>(null);
  const surface = (key: string, w: number, h: number) => {
    let cv = layers.current.get(key);
    if (!cv) {
      cv = document.createElement('canvas');
      layers.current.set(key, cv);
    }
    if (cv.width !== w) cv.width = w;
    if (cv.height !== h) cv.height = h;
    cv.getContext('2d')!.clearRect(0, 0, w, h);
    return cv;
  };
  const filtered = (
    layer: HTMLCanvasElement,
    target: 'podcast' | 'broll' | 'image',
    key: string,
  ) => {
    const p = latest.current,
      strength = filterStrength(p.plan, target, p.frame);
    if (!strength) return layer;
    let engine = sharpeners.current.get(target);
    if (!engine) {
      engine = new Sharpener();
      sharpeners.current.set(target, engine);
    }
    return engine.apply(layer, strength, key, p.playing);
  };
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const resize = () => {
      const scale = Math.min(
        Math.max(1, el.clientWidth - 16) / format.width,
        Math.max(1, el.clientHeight - 8) / format.height,
      );
      setBox({ width: format.width * scale, height: format.height * scale });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();
    return () => observer.disconnect();
  }, [format]);
  useEffect(() => {
    void Promise.all(
      ['DejaVu Sans', 'Liberation Sans', 'Poppins'].map((name) =>
        document.fonts.load(`600 62px "${name}"`),
      ),
    ).then(() => paint.current(true));
  }, []);
  function visible() {
    const p = latest.current,
      x = atFrame(p.plan, p.frame),
      local = p.frame - x.start;
    return {
      x,
      local,
      items: [
        ...x.s.captions
          .filter((c) => local >= c.start && local < c.end)
          .map((c) => ({
            item: c,
            kind: 'caption' as const,
            style: c.style || p.plan.subtitle_style,
            layer: 0,
          })),
        ...x.s.overlays
          .filter((o) => local >= o.start && local < o.end)
          .map((o) => ({ item: o, kind: 'overlay' as const, style: o.style, layer: o.layer + 1 })),
      ].sort((a, b) => a.layer - b.layer),
    };
  }
  paint.current = (force = false) => {
    const cv = canvas.current,
      v = video.current;
    if (!cv || !v || v.readyState < 2 || v.seeking || buffered.current) return;
    const ctx = cv.getContext('2d')!,
      p = latest.current,
      { x, local, items } = visible(),
      w = cv.width,
      h = cv.height;
    const key =
      p.frame +
      ':' +
      w +
      ':' +
      h +
      ':' +
      [...chosen.current.values()]
        .map((v) =>
          v instanceof HTMLVideoElement ? v.currentSrc + ':' + v.currentTime.toFixed(3) : 'cached',
        )
        .join('|');
    if (
      !force &&
      lastPaint.current?.plan === p.plan &&
      lastPaint.current.selection === p.selection &&
      lastPaint.current.key === key
    )
      return;
    lastPaint.current = { plan: p.plan, selection: p.selection, key };
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, w, h);
    const frameLimits = Object.fromEntries([
      ['podcast', p.sourceFrames],
      ...p.videoAssets.map((a) => [a.id, a.frames]),
    ]);
    for (const { span, weight } of visualLayers(p.plan, p.frame, frameLimits)) {
      const node = chosen.current.get(span.key + '@' + span.start);
      if (!node || !weight) continue;
      const layer = surface('visual', w, h),
        lc = layer.getContext('2d')!,
        t = span.transform;
      lc.fillStyle = '#000';
      lc.fillRect(0, 0, w, h);
      const pane = (position: number, top: number, ph: number) => {
        const nw = node instanceof HTMLVideoElement ? node.videoWidth : node.width,
          nh = node instanceof HTMLVideoElement ? node.videoHeight : node.height;
        const scale =
            (t.mode === 'fit' ? Math.min(w / nw, ph / nh) : Math.max(w / nw, ph / nh)) * t.scale,
          vw = nw * scale,
          vh = nh * scale;
        lc.save();
        lc.beginPath();
        lc.rect(0, top, w, ph);
        lc.clip();
        lc.drawImage(
          node,
          t.legacy_center
            ? Math.max(w - vw, Math.min(0, w / 2 - vw * position))
            : (w - vw) * position,
          top + (ph - vh) * t.y,
          vw,
          vh,
        );
        lc.restore();
      };
      if (t.mode === 'split') {
        pane(t.x, 0, h / 2);
        pane(t.b, h / 2, h / 2);
      } else pane(t.x, 0, h);
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = weight;
      ctx.drawImage(filtered(layer, span.kind, span.key), 0, 0);
      ctx.restore();
    }
    paintFlash(ctx, p.plan, p.frame, w, h);
    for (const entry of items) {
      const { item, style } = entry;
      if ('kind' in item && item.kind === 'image') {
        const im = images.current.get(item.asset_id!);
        if (im?.complete) {
          const layer = surface('image', w, h),
            lc = layer.getContext('2d')!;
          lc.save();
          lc.globalAlpha = style.opacity;
          lc.translate(style.x * w, style.y * h);
          lc.rotate((style.rotation * Math.PI) / 180);
          lc.drawImage(
            im,
            (-style.width * w) / 2,
            (-style.height * h) / 2,
            style.width * w,
            style.height * h,
          );
          lc.restore();
          ctx.drawImage(filtered(layer, 'image', item.id), 0, 0);
        }
      } else drawText(ctx, item, style, local, w, h);
      if (p.selection?.id === item.id) {
        ctx.save();
        ctx.strokeStyle = '#5eead4';
        ctx.lineWidth = w / 400;
        ctx.setLineDash([w / 100, w / 150]);
        ctx.strokeRect(
          (style.x - style.width / 2) * w,
          (style.y - style.height / 2) * h,
          style.width * w,
          style.height * h,
        );
        ctx.fillStyle = '#5eead4';
        ctx.fillRect(
          (style.x + style.width / 2) * w - w / 120,
          (style.y + style.height / 2) * h - w / 120,
          w / 60,
          w / 60,
        );
        ctx.restore();
      }
    }
  };
  useEffect(() => {
    for (const a of props.assets) {
      if (images.current.has(a.id)) continue;
      const im = new Image();
      im.onload = () => paint.current(true);
      im.src = a.url;
      images.current.set(a.id, im);
    }
  }, [props.assets]);
  useEffect(() => {
    const v = video.current!,
      manager = new PreviewMedia(container.current!, (s) => latest.current.onQualityWarning(s));
    media.current = manager;
    let stopped = false,
      raf = 0,
      mainCallback = 0,
      mainTime = NaN,
      lastFrame = -1,
      lastPlay = false,
      lastSegment = '',
      preparing = false,
      preparationKey = '',
      generation = 0,
      failed = false,
      mainWaiting = 0,
      awaitingFirstFrame = true;
    const presented = (_now: number, m?: VideoFrameCallbackMetadata) => {
      mainTime = m?.mediaTime ?? v.currentTime;
      if (!stopped && typeof v.requestVideoFrameCallback === 'function')
        mainCallback = v.requestVideoFrameCallback(presented);
    };
    const ready = () => {
      mainTime = v.currentTime;
    };
    v.addEventListener('loadeddata', ready);
    v.addEventListener('seeked', ready);
    if (typeof v.requestVideoFrameCallback === 'function')
      mainCallback = v.requestVideoFrameCallback(presented);
    function need(
      span: ReturnType<typeof visualSpans>[number],
      frame: number,
      active: boolean,
    ): MediaNeed {
      const p = latest.current,
        a = p.videoAssets.find((a) => a.id === span.asset_id);
      const proxy = span.kind === 'podcast' ? p.src : a?.proxy_url || '';
      return {
        id: (span.asset_id || 'podcast') + '@' + (span.source_in - span.start),
        assetId: span.asset_id || 'podcast',
        url:
          span.kind === 'podcast' ? p.src : p.quality === 'sharp' ? a?.source_url || proxy : proxy,
        proxy,
        time: Math.max(0, span.source_in + (active ? frame - span.start : 0)) / 30,
        active,
      };
    }
    const tick = () => {
      if (stopped) return;
      const p = latest.current,
        row = atFrame(p.plan, p.frame),
        target = (row.s.source_in + p.frame - row.start) / 30;
      const spans = visualSpans(p.plan),
        inventory = spans.map((s) => need(s, s.start, true));
      const extras = p.plan.segments.flatMap((s) => [
        ...s.overlays
          .filter((o) => o.kind === 'image')
          .map((o) => ({
            kind: 'image' as const,
            url: p.assets.find((a) => a.id === o.asset_id)?.url || '',
            time: 0,
          })),
        ...(s.audio || []).map((a) => ({
          kind: 'audio' as const,
          url: p.audioAssets.find((x) => x.id === a.asset_id)?.url || '',
          time: a.source_in / 30,
        })),
      ]);
      const count = inventory.length + extras.length;
      const key = JSON.stringify([inventory.map((n) => [n.url, n.time]), extras]) + p.retry;
      if (key !== preparationKey) {
        preparationKey = key;
        preparing = true;
        failed = false;
        awaitingFirstFrame = true;
        const current = ++generation;
        v.pause();
        manager.playback([], false);
        buffered.current = true;
        p.onBuffering(true);
        p.onStatus({ phase: 'preparing', completed: 0, total: count });
        void (async () => {
          await manager.prepare(
            inventory,
            () => stopped || generation !== current,
            (completed) => {
              if (!stopped && generation === current)
                latest.current.onStatus({ phase: 'preparing', completed, total: count });
            },
          );
          for (let i = 0; i < extras.length; i++) {
            if (stopped || generation !== current) return;
            const x = extras[i];
            await manager.prepareExtra(
              x.url,
              x.kind,
              x.time,
              () => stopped || generation !== current,
            );
            if (!stopped && generation === current)
              latest.current.onStatus({
                phase: 'preparing',
                completed: inventory.length + i + 1,
                total: count,
              });
          }
        })()
          .then(() => {
            if (stopped || generation !== current) return;
            preparing = false;
            lastSegment = '';
          })
          .catch((e) => {
            if (stopped || generation !== current) return;
            failed = true;
            preparing = false;
            p.onStatus({
              phase: 'failed',
              completed: 0,
              total: count,
              error: (e as Error).message,
            });
          });
      }
      if (preparing || failed) {
        lastFrame = p.frame;
        lastPlay = p.playing;
        raf = requestAnimationFrame(tick);
        return;
      }
      const explicit =
        (!p.playing && p.frame !== lastFrame) || p.playing !== lastPlay || lastSegment !== row.s.id;
      if (
        v.readyState &&
        !v.seeking &&
        (explicit || Math.abs(v.currentTime - target) > 0.45) &&
        Math.abs(v.currentTime - target) > 0.018
      ) {
        v.currentTime = target;
        mainTime = NaN;
      }
      if (typeof v.requestVideoFrameCallback !== 'function' && !v.seeking && v.readyState >= 2)
        mainTime = v.currentTime;
      const limits = Object.fromEntries([
        ['podcast', p.sourceFrames],
        ...p.videoAssets.map((a) => [a.id, a.frames]),
      ]);
      const active = visualLayers(p.plan, p.frame, limits);
      const needs = spans.flatMap((span) => {
        const used = active.some((x) => x.span.key === span.key && x.span.start === span.start);
        if (!used && (span.start < p.frame || span.start - p.frame > 90)) return [];
        return [need(span, p.frame, used)];
      });
      const state = manager.update(needs, p.playing);
      chosen.current = new Map(
        active.flatMap(({ span }) => {
          const value = state.chosen.get(need(span, p.frame, true).id);
          return value ? [[span.key + '@' + span.start, value] as const] : [];
        }),
      );
      const mainReady =
        v.readyState >= 2 &&
        v.videoWidth > 0 &&
        !v.seeking &&
        Number.isFinite(mainTime) &&
        Math.abs(mainTime - target) < (p.playing ? 0.45 : 0.05);
      const wait = !state.ready || !mainReady;
      if (!mainReady) {
        mainWaiting ||= performance.now();
      } else mainWaiting = 0;
      if (v.error || (mainWaiting && performance.now() - mainWaiting > 12000))
        manager.error = 'Video podcast belum dapat disiapkan. Periksa sumber lalu coba lagi.';
      if (buffered.current !== wait) {
        buffered.current = wait;
        p.onBuffering(wait);
      }
      if (!wait && awaitingFirstFrame) {
        awaitingFirstFrame = false;
        latest.current.onQualityReady();
      }
      p.onStatus({
        phase: manager.error
          ? 'failed'
          : awaitingFirstFrame
            ? 'preparing'
            : wait
              ? v.seeking
                ? 'seeking'
                : 'waiting'
              : 'ready',
        completed: count,
        total: count,
        error: manager.error || undefined,
      });
      if (manager.error) {
        failed = true;
      }
      const run = p.playing && !wait && !failed;
      manager.playback(needs, run);
      v.volume = (p.plan.source_volume ?? 1) * fadeGain(p.plan.source_fade, p.frame, total(p.plan));
      if (run) {
        if (v.paused) void v.play().catch(() => p.setPlaying(false));
        const local = Math.round(mainTime * 30) - row.s.source_in;
        if (local >= row.s.duration) {
          const next = p.plan.segments[p.plan.segments.findIndex((s) => s.id === row.s.id) + 1];
          if (next) {
            p.setFrame(row.end);
            lastSegment = '';
          } else {
            p.setPlaying(false);
            p.setFrame(row.end - 1);
          }
        } else if (local >= 0 && row.start + local !== p.frame) p.setFrame(row.start + local);
      } else if (!v.paused) v.pause();
      lastFrame = p.frame;
      lastPlay = p.playing;
      lastSegment = row.s.id;
      paint.current();
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      stopped = true;
      generation++;
      cancelAnimationFrame(raf);
      if (mainCallback) v.cancelVideoFrameCallback(mainCallback);
      v.pause();
      manager.dispose();
      v.removeEventListener('loadeddata', ready);
      v.removeEventListener('seeked', ready);
      for (const engine of sharpeners.current.values()) engine.dispose();
      sharpeners.current.clear();
      media.current = null;
    };
  }, [props.src, props.retry]);
  function pointer(e: React.PointerEvent<HTMLCanvasElement>) {
    if (e.button !== 0) return;
    props.setPlaying(false);
    const rect = e.currentTarget.getBoundingClientRect(),
      px = (e.clientX - rect.left) / rect.width,
      py = (e.clientY - rect.top) / rect.height;
    const { x, local, items } = visible();
    const b = x.s.broll?.find((b) => local >= b.start && local < b.end);
    const hit = [...items]
      .reverse()
      .find(
        ({ style: s }) => Math.abs(px - s.x) <= s.width / 2 && Math.abs(py - s.y) <= s.height / 2,
      );
    props.select(
      hit
        ? { kind: hit.kind, id: hit.item.id, segmentId: x.s.id }
        : { kind: b ? 'broll' : 'video', id: b?.id || x.s.id, segmentId: x.s.id },
    );
    const initial = hit ? { ...hit.style } : { ...(b?.transform || x.s.transform) };
    const resize =
      hit &&
      Math.abs(px - hit.style.x - hit.style.width / 2) < 0.045 &&
      Math.abs(py - hit.style.y - hit.style.height / 2) < 0.045;
    props.begin();
    e.currentTarget.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - e.clientX) / rect.width,
        dy = (ev.clientY - e.clientY) / rect.height;
      if (hit) {
        const s = initial as Style;
        latest.current.changeStyle(
          resize
            ? { width: clamp(s.width + dx * 2, 0.02, 2), height: clamp(s.height + dy * 2, 0.02, 2) }
            : { x: clamp(s.x + dx, 0, 1), y: clamp(s.y + dy, 0, 1) },
        );
      } else
        latest.current.changeTransform({
          x: clamp(initial.x - dx, 0, 1),
          y: clamp(initial.y - dy, 0, 1),
        });
    };
    const end = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
      latest.current.commit();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  }
  return (
    <div className="live-stage" ref={stage}>
      <video ref={video} src={props.src} playsInline preload="auto" className="decode-video" />
      <div aria-hidden="true" ref={container} />
      <canvas
        aria-label="Kanvas editor: pilih dan geser elemen"
        ref={canvas}
        width={format.width}
        height={format.height}
        onPointerDown={pointer}
        style={{
          width: box.width,
          height: box.height,
          aspectRatio: `${format.width}/${format.height}`,
        }}
      />
    </div>
  );
}
