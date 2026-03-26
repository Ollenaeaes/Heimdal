import { useCallback, useEffect, useRef } from 'react';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { SpeedSlider } from './SpeedSlider';

function formatTime(date: Date): string {
  return date.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

/**
 * TimelineBar renders playback controls at the bottom of the map during lookback mode.
 * Includes play/pause, speed selector, scrubber, timestamp, and close button.
 * Drives the animation loop via requestAnimationFrame.
 */
export function TimelineBar() {
  const isPlaying = useLookbackStore((s) => s.isPlaying);
  const playbackSpeed = useLookbackStore((s) => s.playbackSpeed);
  const currentTime = useLookbackStore((s) => s.currentTime);
  const dateRange = useLookbackStore((s) => s.dateRange);
  const tracks = useLookbackStore((s) => s.tracks);
  const play = useLookbackStore((s) => s.play);
  const pause = useLookbackStore((s) => s.pause);
  const setSpeed = useLookbackStore((s) => s.setSpeed);
  const seekToTime = useLookbackStore((s) => s.seekToTime);
  const deactivate = useLookbackStore((s) => s.deactivate);

  const rafRef = useRef<number>(0);
  const lastFrameRef = useRef<number>(0);

  // Animation loop
  useEffect(() => {
    if (!isPlaying) {
      lastFrameRef.current = 0;
      return;
    }

    function tick(now: number) {
      if (lastFrameRef.current === 0) {
        lastFrameRef.current = now;
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const deltaMs = now - lastFrameRef.current;
      lastFrameRef.current = now;

      const { currentTime: ct, dateRange: dr, playbackSpeed: speed } = useLookbackStore.getState();
      // 1x = real-time (1ms real = 1ms simulated). Higher speeds are multiples.
      const advanceMs = deltaMs * speed;
      const nextMs = ct.getTime() + advanceMs;

      if (nextMs >= dr.end.getTime()) {
        useLookbackStore.getState().seekToTime(dr.end);
        useLookbackStore.getState().pause();
        return;
      }

      useLookbackStore.getState().seekToTime(new Date(nextMs));
      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying]);

  // Keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === ' ' || e.key === 'k') {
        e.preventDefault();
        const { isPlaying: p } = useLookbackStore.getState();
        p ? pause() : play();
      } else if (e.key === 'Escape') {
        deactivate();
      }
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [play, pause, deactivate]);

  const totalMs = dateRange.end.getTime() - dateRange.start.getTime();
  const elapsedMs = currentTime.getTime() - dateRange.start.getTime();
  const progress = totalMs > 0 ? Math.min(100, Math.max(0, (elapsedMs / totalMs) * 100)) : 0;

  const handleScrub = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      seekToTime(new Date(dateRange.start.getTime() + pct * totalMs));
    },
    [seekToTime, dateRange, totalMs],
  );

  const handleScrubDrag = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.buttons !== 1) return;
      handleScrub(e);
    },
    [handleScrub],
  );

  const showGnssOverlay = useLookbackStore((s) => s.showGnssOverlay);
  const gnssOverlayWindow = useLookbackStore((s) => s.gnssOverlayWindow);
  const toggleGnssOverlay = useLookbackStore((s) => s.toggleGnssOverlay);
  const setGnssOverlayWindow = useLookbackStore((s) => s.setGnssOverlayWindow);
  const showAircraftOverlay = useLookbackStore((s) => s.showAircraftOverlay);
  const toggleAircraftOverlay = useLookbackStore((s) => s.toggleAircraftOverlay);

  const tracksLoaded = tracks.size;
  const isLoading = tracksLoaded === 0;

  return (
    <div
      className="absolute bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-col rounded-lg border border-slate-700/50 shadow-2xl overflow-hidden"
      style={{ backgroundColor: 'rgba(10, 14, 23, 0.92)', width: 'clamp(400px, 55%, 900px)' }}
      data-testid="timeline-bar"
    >
      {/* Scrubber track */}
      <div
        className="h-2 cursor-pointer relative group"
        onClick={handleScrub}
        onMouseMove={handleScrubDrag}
        data-testid="timeline-scrubber"
      >
        <div className="absolute inset-0 bg-slate-800" />
        <div
          className="absolute top-0 left-0 h-full bg-blue-500 transition-none"
          style={{ width: `${progress}%` }}
        />
        {/* Thumb */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
          style={{ left: `calc(${progress}% - 6px)` }}
        />
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-3 px-4 py-2">
        {/* Play / Pause */}
        <button
          onClick={() => (isPlaying ? pause() : play())}
          disabled={isLoading}
          className="text-white hover:text-blue-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid="timeline-play-pause"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        {/* Speed slider */}
        <SpeedSlider value={playbackSpeed} onChange={setSpeed} />

        {/* Current timestamp */}
        <span className="font-mono text-xs text-slate-300 ml-2" data-testid="timeline-timestamp">
          {formatTime(currentTime)}
        </span>

        {/* Loading indicator */}
        {isLoading && (
          <span className="text-xs text-slate-500 ml-2">Loading tracks...</span>
        )}

        {/* Track count */}
        {!isLoading && (
          <span className="text-xs text-slate-500 ml-1">
            {tracksLoaded} track{tracksLoaded !== 1 ? 's' : ''}
          </span>
        )}

        {/* Aircraft overlay toggle */}
        <label className="flex items-center gap-1 ml-2 cursor-pointer select-none" data-testid="timeline-aircraft-toggle">
          <input
            type="checkbox"
            checked={showAircraftOverlay}
            onChange={toggleAircraftOverlay}
            className="w-3 h-3 accent-amber-500"
          />
          <span className="text-[0.65rem] text-slate-400">Aircraft</span>
        </label>

        {/* GNSS overlay toggle */}
        <label className="flex items-center gap-1 ml-2 cursor-pointer select-none" data-testid="timeline-gnss-toggle">
          <input
            type="checkbox"
            checked={showGnssOverlay}
            onChange={toggleGnssOverlay}
            className="w-3 h-3 accent-blue-500"
          />
          <span className="text-[0.65rem] text-slate-400">GNSS</span>
        </label>

        {showGnssOverlay && (
          <div className="flex items-center gap-0.5" data-testid="timeline-gnss-window">
            {(['1h', '3h', '6h'] as const).map((w) => (
              <button
                key={w}
                onClick={() => setGnssOverlayWindow(w)}
                className={`px-1 py-0.5 text-[0.6rem] font-mono rounded transition-colors ${
                  gnssOverlayWindow === w
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-slate-700'
                }`}
                data-testid={`timeline-gnss-window-${w}`}
              >
                {w}
              </button>
            ))}
          </div>
        )}

        {/* Close button */}
        <button
          onClick={deactivate}
          className="ml-auto text-slate-400 hover:text-red-400 transition-colors"
          data-testid="timeline-close"
          aria-label="Close lookback"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
