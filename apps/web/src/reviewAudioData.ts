import { useEffect, useState } from 'react';
import { api } from './api';
export type AudioState = {
  audio_status: string;
  waveform_status: string;
  audio_url: string | null;
  version: string | null;
  error: string | null;
  job: { status: string; stage: string; queue_position: number | null } | null;
};
type Peaks = { start: number; step: number; peaks: [number, number][]; version: string };
const cache = new Map<string, { start: number; step: number; values: Int16Array }>();
let cacheSize = 0;
export async function peaks(url: string, signal: AbortSignal) {
  const old = cache.get(url);
  if (old) {
    cache.delete(url);
    cache.set(url, old);
    return old;
  }
  const response = await fetch(url, { signal });
  if (!response.ok) throw Error('Waveform belum tersedia.');
  const data: Peaks = await response.json(),
    result = { start: data.start, step: data.step, values: new Int16Array(data.peaks.flat()) };
  while (cacheSize + result.values.byteLength > 8 * 1024 * 1024 && cache.size) {
    const key = cache.keys().next().value!;
    cacheSize -= cache.get(key)!.values.byteLength;
    cache.delete(key);
  }
  const replaced = cache.get(url);
  if (replaced) cacheSize -= replaced.values.byteLength;
  cache.set(url, result);
  cacheSize += result.values.byteLength;
  return result;
}

export function useReviewAudio(projectId: string) {
  const [state, setState] = useState<AudioState | null>(null),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true,
      asked = false,
      timer = 0;
    const poll = async () => {
      try {
        let next = await api<AudioState>('/projects/' + projectId + '/review-audio');
        if (!live) return;
        if (
          !asked &&
          next.audio_status !== 'missing' &&
          (next.audio_status !== 'ready' || next.waveform_status !== 'ready') &&
          !next.error
        ) {
          asked = true;
          next = await api<AudioState>('/projects/' + projectId + '/review-audio', 'POST');
        }
        if (!live) return;
        setState(next);
        setError('');
        if (
          next.audio_status !== 'missing' &&
          !next.error &&
          (next.audio_status !== 'ready' || next.waveform_status !== 'ready')
        )
          timer = window.setTimeout(poll, 2000);
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    };
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [projectId, retry]);

  return {
    state,
    error,
    retry: async () => {
      try {
        await api('/projects/' + projectId + '/review-audio', 'POST');
        setRetry((v) => v + 1);
      } catch (e) {
        setError((e as Error).message);
      }
    },
  };
}
