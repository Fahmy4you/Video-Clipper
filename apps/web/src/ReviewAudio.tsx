import { useState } from 'react';
import { Play, Pause, Pencil } from 'lucide-react';
import type { Proposal } from './ReviewHighlights';
import { frameLabel } from './components/TimeRangeFields';
import { durationLabel } from './timeRange';
import { useReviewAudio } from './reviewAudioData';
import { useReviewPlayer } from './useReviewPlayer';
import { AudioRevision } from './AudioRevision';
import './review-audio.css';

export function ReviewAudio({
  projectId,
  proposal,
  duration,
  refresh,
  locked,
  onDirty,
}: {
  projectId: string;
  proposal: Proposal;
  duration: number;
  refresh: () => Promise<void>;
  locked: boolean;
  onDirty: (dirty: boolean) => void;
}) {
  const { state, error, retry } = useReviewAudio(projectId),
    [open, setOpen] = useState(false);
  const url = state?.audio_status === 'ready' ? state.audio_url : null;
  const player = useReviewPlayer(url, proposal.start, proposal.end);
  return (
    <section className="panel proposal-section review-audio">
      <h2>Audio sumber</h2>
      {url && <audio ref={player.audio} src={url} preload="metadata" {...player.events} />}
      <div className="compact-audio">
        <button
          type="button"
          className="button secondary"
          disabled={!url}
          aria-label={player.playing ? 'Jeda audio' : 'Putar audio'}
          onClick={() => (player.playing ? player.pause() : void player.play())}
        >
          {player.playing ? <Pause size={18} /> : <Play size={18} />}
        </button>
        <input
          aria-label="Posisi audio highlight"
          type="range"
          min={proposal.start / 30}
          max={proposal.end / 30}
          step={1 / 30}
          disabled={!url}
          value={player.position}
          onChange={(e) => player.seek(+e.target.value)}
        />
        <span>
          {frameLabel(Math.round(player.position * 30), duration)} ·{' '}
          {durationLabel(proposal.end - proposal.start)}
        </span>
      </div>
      {(player.loading || !url) && (
        <p role="status">
          {state?.audio_status === 'missing'
            ? state.error
            : player.loading
              ? 'Memuat audio…'
              : state?.job?.stage || 'Menyiapkan audio sumber…'}
        </p>
      )}
      {(error || state?.error || player.error) && (
        <p role="alert">
          {error || state?.error || player.error}{' '}
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              player.audio.current?.load();
              void retry();
            }}
          >
            Coba lagi
          </button>
        </p>
      )}
      <div>
        <button
          type="button"
          className="button secondary"
          disabled={locked || !url}
          onClick={() => {
            player.pause();
            setOpen(true);
          }}
        >
          <Pencil size={16} />
          Revisi bagian melalui audio
        </button>
      </div>
      {open && state && (
        <AudioRevision
          projectId={projectId}
          proposal={proposal}
          duration={duration}
          state={state}
          onClose={() => {
            setOpen(false);
            onDirty(false);
          }}
          refresh={refresh}
          onDirty={onDirty}
        />
      )}
    </section>
  );
}
