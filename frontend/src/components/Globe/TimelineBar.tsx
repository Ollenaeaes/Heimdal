import { useEffect, useRef, useCallback } from 'react';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { formatTimestampAbsolute } from '../../utils/formatters';

const SPEED_OPTIONS = [1, 5, 100, 500];

/** Detect AIS gaps (>6h) in a track for visual indicators on the timeline. */
function detectGapRanges(
  tracks: Map<number, { timestamp: string }[]>,
  dateRange: { start: Date; end: Date },
): { leftPct: number; widthPct: number }[] {
  const totalMs = dateRange.end.getTime() - dateRange.start.getTime();
  if (totalMs <= 0) return [];

  const gaps: { leftPct: number; widthPct: number }[] = [];
  const GAP_THRESHOLD_MS = 6 * 60 * 60 * 1000; // 6 hours

  for (const track of tracks.values()) {
    for (let i = 1; i < track.length; i++) {
      const prevMs = new Date(track[i - 1].timestamp).getTime();
      const currMs = new Date(track[i].timestamp).getTime();
      if (currMs - prevMs >= GAP_THRESHOLD_MS) {
        const left = ((prevMs - dateRange.start.getTime()) / totalMs) * 100;
        const width = ((currMs - prevMs) / totalMs) * 100;
        gaps.push({
          leftPct: Math.max(0, Math.min(100, left)),
          widthPct: Math.max(0, Math.min(100 - left, width)),
        });
      }
    }
  }
  return gaps;
}

export function TimelineBar() {
  const isActive = useLookbackStore((s) => s.isActive);
  const isPlaying = useLookbackStore((s) => s.isPlaying);
  const playbackSpeed = useLookbackStore((s) => s.playbackSpeed);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const tracks = useLookbackStore((s) => s.tracks);
  const play = useLookbackStore((s) => s.play);
  const pause = useLookbackStore((s) => s.pause);
  const setSpeed = useLookbackStore((s) => s.setSpeed);
  const seekToProgress = useLookbackStore((s) => s.seekToProgress);
  const seekToTime = useLookbackStore((s) => s.seekToTime);
  const deactivate = useLookbackStore((s) => s.deactivate);

  const animFrameRef = useRef<number | null>(null);
  const lastTickRef = useRef<number>(0);

  // Calculate progress percentage
  const totalMs = dateRange.end.getTime() - dateRange.start.getTime();
  const elapsedMs = currentTime.getTime() - dateRange.start.getTime();
  const progress = totalMs > 0 ? Math.max(0, Math.min(100, (elapsedMs / totalMs) * 100)) : 0;

  // AIS gap regions
  const gapRegions = detectGapRanges(tracks, dateRange);

  // Animation loop — time-based, not index-based
  useEffect(() => {
    if (!isPlaying || !isActive) return;

    const tick = (timestamp: number) => {
      if (lastTickRef.current === 0) {
        lastTickRef.current = timestamp;
      }

      const deltaSec = (timestamp - lastTickRef.current) / 1000;
      lastTickRef.current = timestamp;

      // Advance by deltaSec * playbackSpeed real seconds
      const advanceMs = deltaSec * playbackSpeed * 1000;

      const state = useLookbackStore.getState();
      const newTimeMs = state.currentTime.getTime() + advanceMs;

      if (newTimeMs >= state.dateRange.end.getTime()) {
        seekToTime(state.dateRange.end);
        pause();
        return;
      }

      seekToTime(new Date(newTimeMs));
      animFrameRef.current = requestAnimationFrame(tick);
    };

    lastTickRef.current = 0;
    animFrameRef.current = requestAnimationFrame(tick);

    return () => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [isPlaying, isActive, playbackSpeed, seekToTime, pause]);

  const handleScrubberClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const percent = (x / rect.width) * 100;
      seekToProgress(Math.max(0, Math.min(100, percent)));
    },
    [seekToProgress],
  );

  const handleClose = useCallback(() => {
    deactivate();
  }, [deactivate]);

  if (!isActive) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 h-[60px] bg-[#111827]/90 backdrop-blur-md border-t border-[#1F2937] z-[60] flex items-center gap-3 px-4"
      data-testid="timeline-bar"
    >
      {/* Play/Pause */}
      <button
        onClick={() => (isPlaying ? pause() : play())}
        className="w-8 h-8 flex items-center justify-center bg-[#1F2937] hover:bg-[#374151] rounded text-gray-300 hover:text-white transition-colors shrink-0"
        aria-label={isPlaying ? 'Pause' : 'Play'}
        data-testid="timeline-play-pause"
      >
        {isPlaying ? '\u23F8' : '\u25B6'}
      </button>

      {/* Speed controls */}
      <div className="flex items-center gap-1 shrink-0" data-testid="timeline-speed-controls">
        {SPEED_OPTIONS.map((speed) => (
          <button
            key={speed}
            onClick={() => setSpeed(speed)}
            className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
              playbackSpeed === speed
                ? 'bg-[#3B82F6] text-white'
                : 'bg-[#1F2937] text-gray-400 hover:text-white'
            }`}
            data-testid={`timeline-speed-${speed}x`}
          >
            {speed}x
          </button>
        ))}
      </div>

      {/* Scrubber */}
      <div className="flex-1 flex flex-col justify-center gap-0.5">
        <div
          className="relative h-3 bg-[#1F2937] rounded cursor-pointer"
          onClick={handleScrubberClick}
          data-testid="timeline-scrubber"
        >
          {/* AIS gap regions (red) */}
          {gapRegions.map((gap, i) => (
            <div
              key={`gap-${i}`}
              className="absolute top-0 bottom-0 bg-red-900/60 z-10"
              style={{ left: `${gap.leftPct}%`, width: `${gap.widthPct}%` }}
              data-testid={`timeline-gap-${i}`}
            />
          ))}

          {/* Progress fill */}
          <div
            className="absolute top-0 bottom-0 bg-[#3B82F6]/30 rounded-l z-0"
            style={{ width: `${progress}%` }}
          />

          {/* Playhead */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-[#3B82F6] z-30"
            style={{ left: `${progress}%` }}
            data-testid="timeline-playhead"
          />
        </div>

        {/* Time labels */}
        <div className="flex justify-between text-[0.6rem] text-gray-500 font-mono">
          <span>{formatTimestampAbsolute(dateRange.start.toISOString())}</span>
          <span>{formatTimestampAbsolute(dateRange.end.toISOString())}</span>
        </div>
      </div>

      {/* Current timestamp */}
      <div className="text-xs text-gray-300 font-mono whitespace-nowrap shrink-0" data-testid="timeline-current-time">
        {formatTimestampAbsolute(currentTime.toISOString())}
      </div>

      {/* Close button */}
      <button
        onClick={handleClose}
        className="w-8 h-8 flex items-center justify-center bg-[#1F2937] hover:bg-[#374151] rounded text-gray-400 hover:text-white transition-colors shrink-0"
        aria-label="Close lookback"
        data-testid="timeline-close"
      >
        ✕
      </button>
    </div>
  );
}
