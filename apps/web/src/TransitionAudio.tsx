import { useEffect, useRef } from 'react';
import { api } from './api';
import { atFrame, globalBroll, type Plan } from './editorModel';
import { planSoundEvents, soundWindows, type Effect } from './transitionEffects';
let context: AudioContext | undefined,
  catalogPromise: Promise<Effect[]> | undefined,
  bufferPromise: Promise<AudioBuffer> | undefined;
export const getContext = () => (context ??= new AudioContext({ sampleRate: 48000 }));
export const catalog = () =>
  (catalogPromise ??= api<Effect[]>('/transition-effects').catch((e) => {
    catalogPromise = undefined;
    throw e;
  }));
export function getBuffer(ctx: AudioContext, url: string) {
  return (bufferPromise ??= fetch(url)
    .then((r) => {
      if (!r.ok) throw new Error('Audio efek tidak tersedia.');
      return r.arrayBuffer();
    })
    .then((b) => ctx.decodeAudioData(b))
    .catch((e) => {
      bufferPromise = undefined;
      throw e;
    }));
}
export function TransitionAudio(p: {
  plan: Plan;
  frame: number;
  playing: boolean;
  onError: (message: string) => void;
}) {
  const latest = useRef(p);
  latest.current = p;
  const signature = JSON.stringify([
    p.plan.transitions,
    p.plan.segments.map((s) => ({ duration: s.duration, broll: s.broll })),
  ]);
  useEffect(() => {
    if (!planSoundEvents(p.plan).length) return;
    let live = true;
    void catalog()
      .then(async (effects) => {
        const effect = effects.find((e) => e.id === 'camera_shutter');
        if (effect) await getBuffer(getContext(), effect.audio_url);
      })
      .catch((e) => {
        if (live) latest.current.onError((e as Error).message);
      });
    return () => {
      live = false;
    };
  }, [signature]);
  useEffect(() => {
    if (!p.playing || !planSoundEvents(p.plan).length) return;
    let stopped = false,
      waiting = false,
      raf = 0,
      buffer: AudioBuffer | undefined,
      effect: Effect | undefined;
    const ctx = getContext(),
      nodes = new Set<AudioBufferSourceNode>(),
      scheduled = new Set<number>();
    const cancel = () => {
      for (const node of nodes) {
        try {
          node.stop();
        } catch {}
        node.disconnect();
      }
      nodes.clear();
      scheduled.clear();
    };
    const video = document.querySelector<HTMLVideoElement>('.live-stage>.decode-video');
    const tick = () => {
      if (stopped) return;
      const props = latest.current;
      if (
        video &&
        !waiting &&
        !video.paused &&
        !video.seeking &&
        video.readyState >= 2 &&
        buffer &&
        effect &&
        ctx.state === 'running'
      ) {
        const row = atFrame(props.plan, props.frame),
          now = row.start / 30 + video.currentTime - row.s.source_in / 30;
        for (const e of soundWindows(props.plan, effect.samples, effect.sample_rate)) {
          const start = e.start / effect.sample_rate,
            end = (e.start + e.length) / effect.sample_rate;
          if (scheduled.has(e.frame) || end <= now || start > now + 0.3) continue;
          const source = ctx.createBufferSource(),
            gain = ctx.createGain();
          source.buffer = buffer;
          gain.gain.value = e.volume;
          source.connect(gain);
          gain.connect(ctx.destination);
          nodes.add(source);
          scheduled.add(e.frame);
          source.onended = () => {
            nodes.delete(source);
            source.disconnect();
            gain.disconnect();
          };
          const elapsed = Math.max(0, now - start);
          source.start(
            ctx.currentTime + Math.max(0, start - now),
            e.skip / effect.sample_rate + elapsed,
            Math.max(0, end - Math.max(now, start)),
          );
        }
      }
      raf = requestAnimationFrame(tick);
    };
    const stalled = () => {
        waiting = true;
        cancel();
      },
      ready = () => {
        waiting = false;
      };
    video?.addEventListener('seeking', stalled);
    video?.addEventListener('waiting', stalled);
    video?.addEventListener('pause', cancel);
    video?.addEventListener('playing', ready);
    video?.addEventListener('seeked', ready);
    void Promise.all([ctx.resume(), catalog()])
      .then(async ([, effects]) => {
        effect = effects.find((e) => e.id === 'camera_shutter');
        if (!effect) throw new Error('Camera shutter tidak tersedia.');
        buffer = await getBuffer(ctx, effect.audio_url);
      })
      .catch((e) => {
        if (!stopped) latest.current.onError((e as Error).message);
      });
    tick();
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      cancel();
      video?.removeEventListener('seeking', stalled);
      video?.removeEventListener('waiting', stalled);
      video?.removeEventListener('pause', cancel);
      video?.removeEventListener('playing', ready);
      video?.removeEventListener('seeked', ready);
    };
  }, [p.playing, signature]);
  return null;
}
