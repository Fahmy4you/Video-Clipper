import { retargetCut, retargetOutgoing, type BoundaryTransition } from './boundaries';
export type Fade = { in_frames: number; out_frames: number; span: number; offset: number };
export type Transition = {
  kind: 'black' | 'crossfade' | 'none' | 'flash';
  frames: number;
  sound?: 'none' | 'camera_shutter';
  sound_volume?: number;
};
export type Ratio = '9:16' | '16:9' | '1:1' | '4:5' | '4:3';
export const formats: { id: Ratio; width: number; height: number; label: string; hint: string }[] =
  [
    {
      id: '9:16',
      width: 1080,
      height: 1920,
      label: 'Vertikal',
      hint: 'TikTok · Shorts · Reels · Story',
    },
    { id: '16:9', width: 1920, height: 1080, label: 'Horizontal', hint: 'YouTube · TV' },
    { id: '1:1', width: 1080, height: 1080, label: 'Persegi', hint: 'Instagram · Facebook' },
    { id: '4:5', width: 1080, height: 1350, label: 'Portrait', hint: 'Feed Instagram' },
    { id: '4:3', width: 1440, height: 1080, label: 'Klasik', hint: 'Format televisi klasik' },
  ];
export type Style = {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  opacity: number;
  font: 'DejaVu Sans' | 'Liberation Sans' | 'Poppins';
  size: number;
  color: string;
  highlight: string;
  outline: number;
  align: 'left' | 'center' | 'right';
  subtitle_version?: 1 | null;
  subtitle_template?:
    | 'sentence'
    | 'word'
    | 'background'
    | 'reveal'
    | 'reveal_up'
    | 'karaoke'
    | 'karaoke_active'
    | null;
  subtitle_motion?: 'none' | 'fade' | 'zoom' | 'zoom_fade' | 'down' | 'down_fade';
  background?: string;
  karaoke: boolean;
  subtitle_mode?: 'sentence' | 'word';
  subtitle_animation?: 'none' | 'soft_zoom';
};
export type Word = {
  id: string;
  start: number;
  end: number;
  text: string;
  probability?: number | null;
  timing_estimated?: boolean;
};
export type Caption = {
  id: string;
  start: number;
  end: number;
  words: Word[];
  style: Style | null;
};
export type Overlay = {
  id: string;
  kind: 'text' | 'image';
  start: number;
  end: number;
  text: string;
  asset_id: string | null;
  layer: number;
  style: Style;
};
export type AudioItem = {
  id: string;
  asset_id: string;
  start: number;
  end: number;
  source_in: number;
  volume: number;
  fade?: Fade;
};
export type AudioAsset = {
  id: string;
  name: string;
  duration: number;
  frames: number;
  url: string;
  waveform: number[];
  waveform_interval: number;
  origin: string;
};
export type Segment = {
  id: string;
  source_in: number;
  duration: number;
  transform: {
    legacy_center?: boolean;
    mode: 'fit' | 'fill' | 'split';
    x: number;
    y: number;
    scale: number;
    b: number;
  };
  captions: Caption[];
  overlays: Overlay[];
  excluded_word_ids: string[];
  audio?: AudioItem[];
  broll?: Broll[];
};
export type FilterTarget = 'image' | 'podcast' | 'broll';
export type TimelineFilter = {
  id: string;
  kind: 'sharpen';
  start: number;
  end: number;
  strength: number;
  targets: FilterTarget[];
};
export type Plan = {
  transition_version?: 1 | null;
  transitions?: BoundaryTransition[];
  filters?: TimelineFilter[];
  source_fade?: Fade;
  source_volume?: number;
  version: 2;
  fps: 30;
  segments: Segment[];
  subtitle_style: Style;
};
export type Clip = {
  aspect_ratio: Ratio;
  processing_config?: Record<string, unknown>;
  instansi_ids?: string[];
  id: string;
  project_id: string;
  title: string;
  reason: string;
  revision: number;
  fulfills_prompt: boolean;
  plan: Plan;
};
export type Project = {
  ai_combo?: string | null;
  source_id?: string | null;
  workflow?: 'legacy' | 'review';
  highlight_request_counts?: {
    requested: number;
    available: number;
    unfulfilled: number;
    failed: number;
    pending: number;
  };
  review_counts?: { proposals: number; review: number; processing: number; ready: number };
  subtitle_mode?: 'sentence' | 'word';
  subtitle_animation?: 'none' | 'soft_zoom';
  instansi_ids?: string[];
  include_global?: boolean;
  mix_hashtags?: string[];
  visual_mode?: 'podcast' | 'mix';
  id: string;
  url: string;
  title: string;
  duration: number;
  status: string;
  created_at: string;
  updated_at: string;
  gemini_model: string | null;
  aspect_ratio: Ratio;
  highlight_count: number;
  additional_prompt: string;
  analysis_report: {
    subtitle_warning?: string;
    subtitle_model?: string;
    mix_message?: string;
    mix_status?: string;
    requested?: number;
    generated?: number;
    unmet_requests?: string[];
  };
};
export type SourceWord = { start: number; end: number; text: string };
export type Asset = { id: string; name: string; width: number; height: number; url: string };
export type Manifest = {
  status: string;
  proxy_url?: string;
  thumbnail_base?: string;
  thumbnail_interval?: number;
  thumbnail_count?: number;
  waveform?: number[];
  waveform_interval?: number;
  width?: number;
  height?: number;
};
export const uid = () => crypto.randomUUID();
export const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
export const style = (): Style => ({
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
  outline: 3,
  align: 'center',
  karaoke: true,
  subtitle_mode: 'sentence',
  subtitle_animation: 'none',
});
export const total = (p: Plan) => p.segments.reduce((n, s) => n + s.duration, 0);
export const offsets = (p: Plan) => {
  let n = 0;
  return p.segments.map((s) => {
    const start = n;
    n += s.duration;
    return { s, start, end: n };
  });
};
export const atFrame = (p: Plan, f: number) =>
  offsets(p).find((x) => f >= x.start && f < x.end) || offsets(p).at(-1)!;
export const timecode = (f: number) =>
  `${Math.floor(f / 1800)
    .toString()
    .padStart(
      2,
      '0',
    )}:${Math.floor(f / 30) % 60 < 10 ? '0' : ''}${Math.floor(f / 30) % 60}:${Math.floor(f % 30)
    .toString()
    .padStart(2, '0')}`;
export function captionsFor(words: Word[]): Caption[] {
  const out: Caption[] = [];
  let g: Word[] = [];
  const flush = () => {
    if (g.length)
      out.push({ id: uid(), start: g[0].start, end: g.at(-1)!.end, words: g, style: null });
    g = [];
  };
  for (const w of words) {
    if (
      g.length &&
      (g.length >= 5 ||
        g.map((w) => w.text).join(' ').length + w.text.length > 35 ||
        w.start - g.at(-1)!.end > 20 ||
        w.end - g[0].start > 84)
    )
      flush();
    g.push(w);
    if (/[.!?]$/.test(w.text)) flush();
  }
  flush();
  return out;
}
export function blankPlan(end: number, words: SourceWord[] = []): Plan {
  const duration = Math.max(1, Math.round(end * 30));
  return {
    version: 2,
    fps: 30,
    subtitle_style: style(),
    segments: [
      {
        id: uid(),
        source_in: 0,
        duration,
        transform: { legacy_center: false, mode: 'fit', x: 0.5, y: 0.5, scale: 1, b: 0.7 },
        captions: captionsFor(
          words
            .filter((w) => w.start * 30 < duration)
            .map((w) => ({
              id: `w-${Math.round(w.start * 30)}`,
              start: Math.round(w.start * 30),
              end: Math.min(
                duration,
                Math.max(Math.round(w.start * 30) + 1, Math.round(w.end * 30)),
              ),
              text: w.text,
            })),
        ),
        overlays: [],
        excluded_word_ids: [],
      },
    ],
  };
}
export function sliceSegment(s: Segment, a: number, b: number, newId = false): Segment {
  const next = structuredClone(s);
  next.id = newId ? uid() : s.id;
  next.source_in = s.source_in + a;
  next.duration = b - a;
  next.captions = s.captions
    .filter((c) => c.end > a && c.start < b)
    .map((c) => {
      const words = c.words
        .filter((w) => w.end > a && w.start < b)
        .map((w) => ({ ...w, start: Math.max(0, w.start - a), end: Math.min(b - a, w.end - a) }));
      return {
        ...structuredClone(c),
        id: newId ? uid() : c.id,
        start: Math.max(0, c.start - a),
        end: Math.min(b - a, c.end - a),
        words,
      };
    })
    .filter((c) => c.words.length);
  next.audio = (s.audio || [])
    .filter((o) => o.end > a && o.start < b)
    .map((o) => ({
      ...o,
      id: newId ? uid() : o.id,
      fade: { ...fadeOf(o), offset: fadeOf(o).offset + Math.max(0, a - o.start) },
      source_in: o.source_in + Math.max(0, a - o.start),
      start: Math.max(0, o.start - a),
      end: Math.min(b - a, o.end - a),
    }));
  next.broll = (s.broll || [])
    .filter((o) => o.end > a && o.start < b)
    .map((o) => ({
      ...structuredClone(o),
      id: newId ? uid() : o.id,
      visual_id: o.visual_id || o.id,
      source_in: o.source_in + Math.max(0, a - o.start),
      start: Math.max(0, o.start - a),
      end: Math.min(b - a, o.end - a),
      transition_in: o.start < a ? { kind: 'none', frames: 0 } : o.transition_in,
      transition_out: o.end > b ? { kind: 'none', frames: 0 } : o.transition_out,
    }));
  next.overlays = s.overlays
    .filter((o) => o.end > a && o.start < b)
    .map((o) => ({
      ...structuredClone(o),
      id: newId ? uid() : o.id,
      start: Math.max(0, o.start - a),
      end: Math.min(b - a, o.end - a),
    }));
  return next;
}
export function splitSegment(p: Plan, frame: number) {
  const x = atFrame(p, frame),
    cut = frame - x.start;
  if (cut < 30 || x.s.duration - cut < 30) return;
  const i = p.segments.findIndex((s) => s.id === x.s.id);
  const right = sliceSegment(x.s, cut, x.s.duration, true);
  retargetCut(p, 'p:' + x.s.id, 'p:' + right.id, frame);
  p.segments.splice(i, 1, sliceSegment(x.s, 0, cut), right);
}
export function trimSegment(
  p: Plan,
  id: string,
  newIn: number,
  newDuration: number,
  source: SourceWord[],
) {
  const i = p.segments.findIndex((s) => s.id === id),
    old = p.segments[i];
  if (!old || newDuration < 30) return;
  const delta = newIn - old.source_in;
  const n = sliceSegment(old, delta, delta + newDuration);
  n.duration = newDuration;
  const added = source
    .filter((w) => {
      const a = Math.round(w.start * 30),
        b = Math.round(w.end * 30);
      return (
        b > newIn &&
        a < newIn + newDuration &&
        (b <= old.source_in || a >= old.source_in + old.duration) &&
        !old.excluded_word_ids.includes(`w-${a}`)
      );
    })
    .map((w) => ({
      id: `w-${Math.round(w.start * 30)}`,
      start: Math.max(0, Math.round(w.start * 30) - newIn),
      end: Math.min(
        newDuration,
        Math.max(Math.round(w.start * 30) + 1, Math.round(w.end * 30)) - newIn,
      ),
      text: w.text,
    }))
    .filter((w) => w.end > w.start);
  n.captions.push(...captionsFor(added));
  n.captions.sort((a, b) => a.start - b.start);
  p.segments[i] = n;
}
export function splitCaption(s: Segment, id: string, frame: number) {
  const i = s.captions.findIndex((c) => c.id === id),
    c = s.captions[i];
  if (!c || c.words.length < 2) return;
  const candidates = c.words.slice(1).map((w) => w.start),
    cut = candidates.reduce((a, b) => (Math.abs(b - frame) < Math.abs(a - frame) ? b : a));
  const left = c.words
      .filter((w) => w.start < cut)
      .map((w) => ({ ...w, end: Math.min(w.end, cut) })),
    right = c.words.filter((w) => w.start >= cut);
  if (!left.length || !right.length) return;
  s.captions.splice(
    i,
    1,
    { ...c, end: cut, words: left },
    { ...structuredClone(c), id: uid(), start: cut, words: right },
  );
}
export function resizeCaption(c: Caption, start: number, end: number) {
  const old = c.end - c.start,
    ratio = (end - start) / old;
  const words = c.words.map((w) => ({
    ...w,
    start: clamp(Math.round(start + (w.start - c.start) * ratio), start, end - 1),
    end: clamp(Math.round(start + (w.end - c.start) * ratio), start + 1, end),
  }));
  c.start = start;
  c.end = end;
  c.words = words.map((w) => ({ ...w, end: Math.max(w.start + 1, w.end) }));
}
export function replaceCaptionText(c: Caption, text: string) {
  const tokens = text.trim().split(/\s+/).filter(Boolean),
    old = c.words;
  if (tokens.length === old.length) {
    old.forEach((w, i) => {
      if (w.text !== tokens[i]) {
        w.text = tokens[i];
        w.probability = null;
      }
    });
    return;
  }
  if (tokens.length > c.end - c.start) return;
  // Longest common subsequence retains timing anchors for unchanged words.
  const norm = (x: string) => x.toLocaleLowerCase().replace(/[.,!?;:]/g, ''),
    dp = Array.from({ length: old.length + 1 }, () => new Uint16Array(tokens.length + 1));
  for (let i = old.length - 1; i >= 0; i--)
    for (let j = tokens.length - 1; j >= 0; j--)
      dp[i][j] =
        norm(old[i].text) === norm(tokens[j])
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const anchors = new Map<number, Word>();
  let i = 0,
    j = 0;
  while (i < old.length && j < tokens.length) {
    if (norm(old[i].text) === norm(tokens[j])) {
      anchors.set(j, { ...old[i], text: tokens[j] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  const out: Word[] = [];
  let at = 0;
  while (at < tokens.length) {
    const anchor = anchors.get(at);
    if (anchor) {
      out.push(anchor);
      at++;
      continue;
    }
    let end = at + 1;
    while (end < tokens.length && !anchors.has(end)) end++;
    let left = out.at(-1)?.end ?? c.start,
      right = anchors.get(end)?.start ?? c.end;
    // If no gap exists, retain the anchors and explicitly mark the local estimate.
    if (right - left < end - at) {
      left = Math.max(c.start, right - (end - at));
    }
    for (let k = at; k < end; k++) {
      const a = left + Math.floor(((right - left) * (k - at)) / (end - at)),
        b = left + Math.floor(((right - left) * (k - at + 1)) / (end - at));
      out.push({
        id: uid(),
        start: clamp(a, c.start, c.end - 1),
        end: clamp(Math.max(a + 1, b), c.start + 1, c.end),
        text: tokens[k],
        timing_estimated: true,
        probability: null,
      });
    }
    at = end;
  }
  c.words = out;
}

export function resizeAudio(item: AudioItem, start: number, end: number, assetFrames: number) {
  const delta = start - item.start;
  const source = item.source_in + delta;
  const sourceIn = clamp(source, 0, Math.max(0, assetFrames - 1));
  const a = start + (sourceIn - source);
  if (item.fade?.span)
    item.fade = { ...item.fade, offset: Math.max(0, item.fade.offset + a - item.start) };
  item.start = a;
  item.source_in = sourceIn;
  item.end = Math.max(a + 1, Math.min(end, a + assetFrames - sourceIn));
}

// End is exclusive: select the last visible frame when the playhead has passed.
export const selectionFrame = (frame: number, start: number, end: number) =>
  clamp(frame, start, Math.max(start, end - 1));
export type TimelineSelection = {
  kind: 'video' | 'caption' | 'overlay' | 'audio' | 'broll' | 'filter' | 'transition';
  id: string;
  segmentId: string;
};
export function duplicateItem(p: Plan, sel: TimelineSelection): TimelineSelection | null {
  if (sel.kind === 'filter') {
    const item = p.filters?.find((f) => f.id === sel.id);
    if (!item) return null;
    const copy = { ...structuredClone(item), id: uid() };
    p.filters!.push(copy);
    return { ...sel, id: copy.id };
  }
  const s = p.segments.find((s) => s.id === sel.segmentId);
  if (!s || sel.kind === 'broll') return null;
  if (sel.kind === 'video') {
    const copy = sliceSegment(s, 0, s.duration, true);
    copy.captions.forEach((c) => c.words.forEach((w) => (w.id = uid())));
    const keys = new Map<string, string>([['p:' + s.id, 'p:' + copy.id]]);
    copy.broll?.forEach((b, i) => {
      keys.set('b:' + (s.broll![i].visual_id || s.broll![i].id), 'b:' + b.id);
      b.visual_id = b.id;
    });
    const inner = (p.transitions || [])
      .filter((t) => keys.has(t.left) && keys.has(t.right))
      .map((t) => {
        const left = keys.get(t.left)!,
          right = keys.get(t.right)!;
        return { id: left + '|' + right, left, right, value: { ...t.value } };
      });
    (p.transitions ??= []).push(...inner);
    p.segments.splice(p.segments.indexOf(s) + 1, 0, copy);
    return { kind: 'video', id: copy.id, segmentId: copy.id };
  }
  if (sel.kind === 'caption') {
    const item = s.captions.find((x) => x.id === sel.id);
    if (!item) return null;
    const copy = structuredClone(item);
    copy.id = uid();
    const delta = item.end + (item.end - item.start) <= s.duration ? item.end - item.start : 0;
    copy.start += delta;
    copy.end += delta;
    copy.words.forEach((w) => {
      w.id = uid();
      w.start += delta;
      w.end += delta;
    });
    s.captions.push(copy);
    return { ...sel, id: copy.id };
  }
  if (sel.kind === 'audio') {
    const item = s.audio?.find((x) => x.id === sel.id);
    if (!item) return null;
    const copy = { ...item, id: uid() };
    if (item.end + item.end - item.start <= s.duration) {
      copy.start = item.end;
      copy.end = copy.start + item.end - item.start;
    }
    s.audio!.push(copy);
    return { ...sel, id: copy.id };
  }
  const item = s.overlays.find((x) => x.id === sel.id);
  if (!item) return null;
  const copy = structuredClone(item);
  copy.id = uid();
  copy.layer = Math.min(100, Math.max(0, ...s.overlays.map((o) => o.layer)) + 1);
  s.overlays.push(copy);
  return { ...sel, id: copy.id };
}

export type Broll = {
  visual_id?: string | null;
  id: string;
  asset_id: string;
  start: number;
  end: number;
  source_in: number;
  reason: string;
  transform: Segment['transform'];
  transition_in: Transition;
  transition_out: Transition;
};
export type VideoAsset = {
  created_at: string;
  scope: 'global' | 'instansi';
  instansi_ids: string[];
  instansi_names: string[];
  id: string;
  title: string;
  hashtags: string[];
  hashtag_ids: string[];
  explain: string;
  scenes: { start: number; end: number; explain: string }[];
  duration: number;
  frames: number;
  width: number;
  height: number;
  status: string;
  error: string | null;
  archived: boolean;
  revision: number;
  source_url: string;
  proxy_url: string;
  thumbnail_url: string;
  thumbnail_base: string;
};
export const emptyFade = (): Fade => ({ in_frames: 0, out_frames: 0, span: 0, offset: 0 });
export const fadeOf = (a: AudioItem): Fade => ({
  ...emptyFade(),
  ...a.fade,
  span: a.fade?.span || a.end - a.start,
});
export function fadeGain(f: Fade | undefined, frame: number, length: number) {
  if (!f) return 1;
  const span = f.span || length,
    x = frame + f.offset;
  return clamp(
    Math.min(
      1,
      f.in_frames ? x / Math.min(f.in_frames, span) : 1,
      f.out_frames ? (span - x) / Math.min(f.out_frames, span) : 1,
    ),
    0,
    1,
  );
}
export function brollLimits(item: Broll, items: Broll[], duration: number, frames: number) {
  const sorted = [...items].sort((a, b) => a.start - b.start),
    i = sorted.findIndex((b) => b.id === item.id),
    prev = i ? sorted[i - 1].end : 0,
    next = i + 1 < sorted.length ? sorted[i + 1].start : duration;
  return [true, false].map((enter) => {
    const edge = enter ? item.transition_in : item.transition_out,
      half = Math.floor(
        Math.min(
          edge.frames / 2,
          (item.end - item.start) / 2,
          (enter ? item.start - prev : next - item.end) / 2,
        ),
      );
    let kind = edge.kind;
    if (
      kind === 'crossfade' &&
      (enter ? item.source_in < half : item.source_in + item.end - item.start + half > frames)
    )
      kind = 'black';
    return { kind, half: kind === 'none' ? 0 : half, fallback: kind !== edge.kind };
  });
}
export function brollWeights(
  item: Broll,
  items: Broll[],
  duration: number,
  frames: number,
  f: number,
) {
  const limits = brollLimits(item, items, duration, frames),
    [a, b] = limits.map((e) => (e.kind === 'flash' ? { ...e, half: 0 } : e)),
    up = a.half
      ? a.kind === 'crossfade'
        ? clamp((f - item.start + a.half) / (2 * a.half), 0, 1)
        : clamp((f - item.start) / a.half, 0, 1)
      : +(f >= item.start),
    down = b.half
      ? b.kind === 'crossfade'
        ? clamp((item.end + b.half - f) / (2 * b.half), 0, 1)
        : clamp((item.end - f) / b.half, 0, 1)
      : +(f < item.end);
  const before =
      a.kind === 'crossfade'
        ? 1 - up
        : a.half
          ? clamp((item.start - f) / a.half, 0, 1)
          : +(f < item.start),
    after =
      b.kind === 'crossfade'
        ? 1 - down
        : b.half
          ? clamp((f - item.end) / b.half, 0, 1)
          : +(f >= item.end);
  return { base: Math.max(before, after), clip: Math.min(up, down) };
}
export const brollFits = (s: Segment, a: number, b: number, except?: string) =>
  a >= 0 &&
  b > a &&
  b <= s.duration &&
  !(s.broll || []).some((x) => x.id !== except && a < x.end && b > x.start);

export const globalBroll = (p: Plan) =>
  offsets(p).flatMap((r) =>
    (r.s.broll || []).map((b) => ({
      ...b,
      start: b.start + r.start,
      end: b.end + r.start,
      segmentId: r.s.id,
    })),
  );

export function placeBroll(
  p: Plan,
  item: Broll,
  start: number,
  end: number,
  replaceId?: string,
): TimelineSelection | null {
  if (
    start < 0 ||
    end <= start ||
    end > total(p) ||
    globalBroll(p).some((b) => b.id !== replaceId && start < b.end && end > b.start)
  )
    return null;
  if (replaceId)
    for (const s of p.segments) s.broll = (s.broll || []).filter((b) => b.id !== replaceId);
  let selected: TimelineSelection | null = null;
  for (const r of offsets(p)) {
    const a = Math.max(start, r.start),
      b = Math.min(end, r.end);
    if (b <= a) continue;
    const id: string = selected ? uid() : item.id;
    (r.s.broll ??= []).push({
      ...structuredClone(item),
      id,
      start: a - r.start,
      end: b - r.start,
      source_in: item.source_in + a - start,
      transition_in: a === start ? item.transition_in : { kind: 'none', frames: 0 },
      transition_out: b === end ? item.transition_out : { kind: 'none', frames: 0 },
    });
    selected ??= { kind: 'broll', segmentId: r.s.id, id };
  }
  return selected;
}

export function clampFilters(p: Plan) {
  const duration = total(p);
  p.filters = (p.filters || [])
    .filter((f) => f.start < duration)
    .map((f) => ({ ...f, end: Math.min(f.end, duration) }));
}
export function filterStrength(p: Plan, target: FilterTarget, frame: number) {
  return Math.max(
    0,
    ...(p.filters || [])
      .filter((f) => f.targets.includes(target) && frame >= f.start && frame < f.end)
      .map((f) => f.strength),
  );
}
export function splitFilter(p: Plan, id: string, frame: number) {
  const f = p.filters?.find((f) => f.id === id);
  if (!f || frame <= f.start || frame >= f.end) return;
  p.filters!.push({ ...structuredClone(f), id: uid(), start: frame });
  f.end = frame;
}

export function splitBroll(p: Plan, id: string, frame: number) {
  const item = globalBroll(p).find((b) => b.id === id);
  if (!item) return;
  const key = item.visual_id || item.id,
    parts = globalBroll(p).filter((b) => (b.visual_id || b.id) === key);
  const start = Math.min(...parts.map((b) => b.start)),
    end = Math.max(...parts.map((b) => b.end));
  if (frame - start < 30 || end - frame < 30) return;
  const newKey = uid();
  retargetOutgoing(p, 'b:' + key, 'b:' + newKey);
  for (const r of offsets(p)) {
    for (const b of [...(r.s.broll || [])]) {
      if ((b.visual_id || b.id) !== key) continue;
      const a = r.start + b.start,
        z = r.start + b.end;
      if (a >= frame) {
        b.visual_id = newKey;
        if (a === frame) b.transition_in = { kind: 'none', frames: 0 };
      } else if (z > frame) {
        const cut = frame - r.start;
        r.s.broll!.push({
          ...structuredClone(b),
          id: uid(),
          visual_id: newKey,
          start: cut,
          source_in: b.source_in + cut - b.start,
          transition_in: { kind: 'none', frames: 0 },
        });
        b.end = cut;
        b.transition_out = { kind: 'none', frames: 0 };
      } else if (z === frame) b.transition_out = { kind: 'none', frames: 0 };
    }
  }
}
