import type { Plan, Transition, Segment, Broll } from './editorModel';
export const noTransition = (): Transition => ({
  kind: 'none',
  frames: 0,
  sound: 'none',
  sound_volume: 1,
});
export type BoundaryTransition = { id: string; left: string; right: string; value: Transition };
export type VisualSpan = {
  key: string;
  kind: 'podcast' | 'broll';
  start: number;
  end: number;
  source_in: number;
  transform: Segment['transform'];
  segmentId: string;
  asset_id?: string;
  transition_in?: Transition;
  transition_out?: Transition;
};
export type Boundary = BoundaryTransition & {
  frame: number;
  before: VisualSpan | null;
  after: VisualSpan | null;
};
export function visualSpans(p: Plan) {
  const out: VisualSpan[] = [];
  let offset = 0;
  for (const s of p.segments) {
    let cursor = 0;
    const podcast = (a: number, b: number) => {
      if (b > a)
        out.push({
          key: 'p:' + s.id,
          kind: 'podcast',
          start: offset + a,
          end: offset + b,
          source_in: s.source_in + a,
          transform: s.transform,
          segmentId: s.id,
        });
    };
    for (const b of [...(s.broll || [])].sort((a, b) => a.start - b.start)) {
      podcast(cursor, b.start);
      const item: VisualSpan = {
          ...b,
          key: 'b:' + (b.visual_id || b.id),
          kind: 'broll',
          start: offset + b.start,
          end: offset + b.end,
          segmentId: s.id,
        },
        last = out.at(-1);
      if (
        last &&
        last.key === item.key &&
        last.end === item.start &&
        last.source_in + last.end - last.start === item.source_in &&
        JSON.stringify(last.transform) === JSON.stringify(item.transform)
      ) {
        last.end = item.end;
        last.transition_out = item.transition_out;
      } else out.push(item);
      cursor = b.end;
    }
    podcast(cursor, s.duration);
    offset += s.duration;
  }
  return out;
}
export function boundaries(p: Plan): Boundary[] {
  const rows = visualSpans(p),
    stored = new Map((p.transitions || []).map((t) => [t.id, t]));
  if (!rows.length) return [];
  const pairs: [VisualSpan | null, VisualSpan | null][] = [
    [null, rows[0]],
    ...rows.slice(1).map((r, i) => [rows[i], r] as [VisualSpan, VisualSpan]),
    [rows.at(-1)!, null],
  ];
  return pairs.flatMap(([before, after]) => {
    const left = before?.key || 'start',
      right = after?.key || 'end',
      id = left + '|' + right;
    if (left === right) return [];
    const a = before?.kind === 'broll' ? before.transition_out : noTransition(),
      b = after?.kind === 'broll' ? after.transition_in : noTransition();
    const value =
      p.transition_version === 1
        ? stored.get(id)?.value || noTransition()
        : (a && (a.kind !== 'none' || (a.sound && a.sound !== 'none')) ? a : b) || noTransition();
    return [{ id, left, right, value, frame: after?.start ?? before!.end, before, after }];
  });
}
export function normalizeTransitions(p: Plan) {
  let previous: { b: Broll; sid: string; end: number } | null = null,
    offset = 0;
  const seen = new Map<string, { b: Broll; sid: string; end: number }>();
  for (const s of p.segments) {
    for (const b of [...(s.broll || [])].sort((a, b) => a.start - b.start)) {
      const start = offset + b.start,
        end = offset + b.end,
        continuous = (old: { b: Broll; sid: string; end: number } | undefined | null) =>
          old &&
          old.end === start &&
          old.b.asset_id === b.asset_id &&
          old.b.source_in + old.b.end - old.b.start === b.source_in &&
          JSON.stringify(old.b.transform) === JSON.stringify(b.transform);
      if (!b.visual_id) {
        const old = previous?.b,
          same =
            old &&
            previous!.sid !== s.id &&
            continuous(previous) &&
            old.transition_out.kind === 'none' &&
            b.transition_in.kind === 'none';
        b.visual_id = same ? old.visual_id : b.id;
      }
      if (seen.has(b.visual_id!) && !continuous(seen.get(b.visual_id!))) b.visual_id = b.id;
      previous = { b, sid: s.id, end };
      seen.set(b.visual_id!, previous);
    }
    offset += s.duration;
  }
  const edges = boundaries(p);
  p.transition_version = 1;
  p.transitions = edges.map(({ id, left, right, value }) => ({
    id,
    left,
    right,
    value: { ...value },
  }));
}
export function reconcileTransitions(before: Plan, p: Plan) {
  if (before.transition_version !== 1) {
    normalizeTransitions(p);
    return;
  }
  const known = new Set(visualSpans(before).map((s) => s.key)),
    stored = new Map((p.transitions || []).map((t) => [t.id, t]));
  const legacy = { ...p, transition_version: undefined };
  for (const e of boundaries(legacy)) {
    if (
      !stored.has(e.id) &&
      (!known.has(e.left) || !known.has(e.right)) &&
      (e.left.startsWith('b:') || e.right.startsWith('b:'))
    )
      stored.set(e.id, { id: e.id, left: e.left, right: e.right, value: e.value });
  }
  p.transitions = [...stored.values()];
  normalizeTransitions(p);
}
export function retargetOutgoing(p: Plan, oldKey: string, newKey: string) {
  for (const t of p.transitions || [])
    if (t.left === oldKey) {
      t.left = newKey;
      t.id = t.left + '|' + t.right;
    }
}
export function boundaryEvents(p: Plan, frames: Record<string, number> = {}) {
  const edges = boundaries(p),
    duration = p.segments.reduce((n, s) => n + s.duration, 0);
  return edges.map((e) => {
    const requested = e.value.frames / 2,
      distance = Math.min(
        ...edges.filter((x) => x.frame !== e.frame).map((x) => Math.abs(x.frame - e.frame) / 2),
      ),
      half = Math.floor(Math.min(requested, e.frame, duration - e.frame, distance));
    let kind = e.value.kind,
      fallback = false;
    if (kind === 'crossfade' && half)
      for (const span of [e.before, e.after]) {
        const start = span ? span.source_in + e.frame - half - span.start : -1,
          limit = span ? frames[span.asset_id || 'podcast'] : undefined;
        if (start < 0 || (limit !== undefined && start + half * 2 > limit)) {
          kind = 'black';
          fallback = true;
          break;
        }
      }
    return { ...e, requested, half: kind === 'none' ? 0 : half, kind, fallback };
  });
}
export function visualLayers(p: Plan, frame: number, frames: Record<string, number> = {}) {
  const spans = visualSpans(p),
    event = boundaryEvents(p, frames).find(
      (e) =>
        e.half &&
        frame >= e.frame - e.half &&
        frame < e.frame + e.half &&
        ['black', 'crossfade'].includes(e.kind),
    );
  if (event) {
    const { before, after, half } = event,
      x = (frame - event.frame + half) / (2 * half);
    if (event.kind === 'crossfade')
      return [
        before && { span: before, weight: 1 - x },
        after && { span: after, weight: x },
      ].filter(Boolean) as { span: VisualSpan; weight: number }[];
    const span = frame < event.frame ? before : after;
    return span ? [{ span, weight: Math.abs(frame - event.frame) / half }] : [];
  }
  const span = spans.find((s) => frame >= s.start && frame < s.end);
  return span ? [{ span, weight: 1 }] : [];
}

export function retargetCut(p: Plan, oldKey: string, newKey: string, frame: number) {
  const times = new Map(boundaries(p).map((e) => [e.id, e.frame]));
  for (const t of p.transitions || []) {
    const at = times.get(t.id) ?? -1;
    if (t.left === oldKey && at > frame) t.left = newKey;
    if (t.right === oldKey && at >= frame) t.right = newKey;
    t.id = t.left + '|' + t.right;
  }
}
