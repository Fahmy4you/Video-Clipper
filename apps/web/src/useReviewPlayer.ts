import { useEffect, useRef, useState } from 'react';
export function useReviewPlayer(url: string | null, start: number, end: number) {
  const audio = useRef<HTMLAudioElement>(null),
    target = useRef<number | null>(null),
    stop = useRef(end / 30);
  const [position, setPosition] = useState(start / 30),
    [playing, setPlaying] = useState(false),
    [waiting, setWaiting] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState('');
  const bounds = useRef({ start, end });
  bounds.current = { start, end };
  function pause() {
    audio.current?.pause();
  }
  function seek(seconds: number) {
    const value = Math.max(bounds.current.start / 30, Math.min(bounds.current.end / 30, seconds));
    target.current = value;
    setPosition(value);
    if (audio.current?.readyState && !audio.current.seeking) audio.current.currentTime = value;
  }
  async function play(from?: number, to = end / 30) {
    if (!audio.current) return;
    stop.current = to;
    if (from !== undefined) seek(from);
    else if (position >= to - 0.01 || position < start / 30) seek(start / 30);
    try {
      await audio.current.play();
      setError('');
    } catch {
      setError('Audio belum dapat diputar. Coba lagi.');
    }
  }
  useEffect(() => {
    pause();
    seek(start / 30);
    stop.current = end / 30;
  }, [start, end, url]);
  useEffect(() => {
    const element = audio.current;
    let raf = 0,
      last = 0;
    const tick = (now: number) => {
      if (element && !element.paused) {
        if (element.currentTime >= stop.current) {
          element.pause();
          element.currentTime = stop.current;
          setPosition(stop.current);
        } else if (now - last > 80) {
          last = now;
          setPosition(element.currentTime);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      element?.pause();
    };
  }, [url]);
  useEffect(() => {
    if (!waiting) {
      setLoading(false);
      return;
    }
    const t = setTimeout(() => setLoading(true), 400);
    return () => clearTimeout(t);
  }, [waiting]);
  const events = {
    onLoadedMetadata: () => seek(target.current ?? start / 30),
    onSeeking: () => setWaiting(true),
    onSeeked: () => {
      const el = audio.current!;
      if (target.current !== null && Math.abs(el.currentTime - target.current) > 1 / 30) {
        el.currentTime = target.current;
        return;
      }
      target.current = null;
      setPosition(el.currentTime);
      setWaiting(false);
    },
    onWaiting: () => setWaiting(true),
    onCanPlay: () => setWaiting(false),
    onPlaying: () => {
      setPlaying(true);
      setWaiting(false);
    },
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
    onError: () => {
      setWaiting(false);
      setError('Audio gagal dimuat. Coba lagi.');
    },
  };
  return { audio, position, playing, loading, error, events, pause, seek, play };
}
