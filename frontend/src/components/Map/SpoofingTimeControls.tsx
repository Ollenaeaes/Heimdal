import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { SpeedSlider } from './SpeedSlider';

export interface GnssTimeBarProps {
  visible: boolean;
  centerTime: Date;
  windowSize: string; // "6h" | "12h" | "24h" | "3d" | "7d"
  onCenterTimeChange: (time: Date) => void;
  onWindowSizeChange: (size: string) => void;
}

const SLIDER_RANGE_HOURS = 30 * 24; // 30 days in hours

const WINDOW_HOURS: Record<string, number> = {
  '6h': 6,
  '12h': 12,
  '24h': 24,
  '3d': 72,
  '7d': 168,
};

const WINDOW_PRESETS = Object.keys(WINDOW_HOURS);

function formatUTC(d: Date): string {
  const year = d.getUTCFullYear();
  const month = (d.getUTCMonth() + 1).toString().padStart(2, '0');
  const day = d.getUTCDate().toString().padStart(2, '0');
  const hours = d.getUTCHours().toString().padStart(2, '0');
  const mins = d.getUTCMinutes().toString().padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${mins} UTC`;
}

function dateToSliderValue(date: Date, now: Date): number {
  const diffMs = now.getTime() - date.getTime();
  const diffHours = diffMs / 3600_000;
  return Math.max(0, Math.min(SLIDER_RANGE_HOURS, SLIDER_RANGE_HOURS - diffHours));
}

function sliderValueToDate(value: number, now: Date): Date {
  return new Date(now.getTime() - (SLIDER_RANGE_HOURS - value) * 3600_000);
}

export function GnssTimeBar({
  visible,
  centerTime,
  windowSize,
  onCenterTimeChange,
  onWindowSizeChange,
}: GnssTimeBarProps) {
  const now = useMemo(() => new Date(), []);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(60); // 1 min/sec default
  const rafRef = useRef<number>(0);
  const lastFrameRef = useRef<number>(0);
  const centerTimeRef = useRef(centerTime);
  useEffect(() => { centerTimeRef.current = centerTime; }, [centerTime]);

  const sliderValue = useMemo(() => dateToSliderValue(centerTime, now), [centerTime, now]);
  const windowHours = WINDOW_HOURS[windowSize] ?? 24;
  const halfWindowHours = windowHours / 2;

  // Window highlight position (percentage-based)
  const highlightLeft = Math.max(0, ((sliderValue - halfWindowHours) / SLIDER_RANGE_HOURS) * 100);
  const highlightWidth = Math.min(
    100 - highlightLeft,
    (windowHours / SLIDER_RANGE_HOURS) * 100,
  );

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

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

      const advanceMs = deltaMs * playbackSpeed;
      const nextTime = new Date(centerTimeRef.current.getTime() + advanceMs);

      // Stop at "now"
      if (nextTime.getTime() >= Date.now()) {
        onCenterTimeChange(new Date());
        setIsPlaying(false);
        return;
      }

      onCenterTimeChange(nextTime);
      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [isPlaying, playbackSpeed, onCenterTimeChange]);

  const debouncedCenterTimeChange = useCallback(
    (date: Date) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onCenterTimeChange(date);
      }, 300);
    },
    [onCenterTimeChange],
  );

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setIsPlaying(false);
      const value = Number(e.target.value);
      const date = sliderValueToDate(value, now);
      debouncedCenterTimeChange(date);
    },
    [now, debouncedCenterTimeChange],
  );

  const handleNow = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    onCenterTimeChange(new Date());
  }, [onCenterTimeChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === ' ') {
        e.preventDefault();
        setIsPlaying((p) => !p);
        return;
      }

      let nudgeHours = 0;
      if (e.key === 'ArrowLeft') nudgeHours = e.shiftKey ? -6 : -1;
      else if (e.key === 'ArrowRight') nudgeHours = e.shiftKey ? 6 : 1;
      else return;

      e.preventDefault();
      const newValue = Math.max(0, Math.min(SLIDER_RANGE_HOURS, sliderValue + nudgeHours));
      const date = sliderValueToDate(newValue, now);
      onCenterTimeChange(date);
    },
    [sliderValue, now, onCenterTimeChange],
  );

  if (!visible) return null;

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-2">
      {/* Current time label */}
      <div className="text-[11px] text-slate-400 bg-slate-900/80 px-3 py-1 rounded-full backdrop-blur-sm">
        {formatUTC(centerTime)}
      </div>

      {/* Preset buttons + Now + Playback controls */}
      <div className="flex items-center gap-1 bg-slate-900/90 backdrop-blur-sm rounded-lg px-2 py-1.5 border border-slate-700/50">
        {/* Play/Pause button */}
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          className="text-slate-300 hover:text-amber-400 transition-colors mr-1"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        <span className="text-[10px] text-slate-500 uppercase tracking-wider mr-1">GNSS</span>
        {WINDOW_PRESETS.map((preset) => (
          <button
            key={preset}
            onClick={() => onWindowSizeChange(preset)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              windowSize === preset
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
            }`}
          >
            {preset}
          </button>
        ))}
        <div className="w-px h-4 bg-slate-700 mx-1" />
        <button
          onClick={handleNow}
          className="px-2.5 py-1 rounded text-xs font-medium transition-colors bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-500/30"
        >
          Now
        </button>

        {/* Speed slider — visible when playing */}
        {isPlaying && (
          <>
            <div className="w-px h-4 bg-slate-700 mx-1" />
            <SpeedSlider value={playbackSpeed} onChange={setPlaybackSpeed} />
          </>
        )}
      </div>

      {/* Timeline slider with window highlight */}
      <div
        className="flex items-center gap-3 bg-slate-900/90 backdrop-blur-sm rounded-lg px-4 py-2 border border-slate-700/50 w-[500px]"
        onKeyDown={handleKeyDown}
      >
        <span className="text-[10px] text-slate-500 whitespace-nowrap">-30d</span>
        <div className="relative flex-1 h-6 flex items-center">
          {/* Track background */}
          <div className="absolute inset-x-0 h-1.5 bg-slate-700 rounded" />
          {/* Window highlight */}
          <div
            className="absolute h-1.5 bg-amber-500/20 rounded pointer-events-none"
            style={{
              left: `${highlightLeft}%`,
              width: `${highlightWidth}%`,
            }}
          />
          {/* Range input */}
          <input
            type="range"
            min={0}
            max={SLIDER_RANGE_HOURS}
            step={1}
            value={sliderValue}
            onChange={handleSliderChange}
            className="relative w-full h-1.5 appearance-none bg-transparent cursor-pointer z-10
              [&::-webkit-slider-thumb]:appearance-none
              [&::-webkit-slider-thumb]:w-3
              [&::-webkit-slider-thumb]:h-3
              [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:bg-amber-400
              [&::-webkit-slider-thumb]:border-2
              [&::-webkit-slider-thumb]:border-amber-500
              [&::-webkit-slider-thumb]:shadow-[0_0_6px_rgba(245,158,11,0.5)]
              [&::-webkit-slider-thumb]:cursor-pointer
              [&::-moz-range-thumb]:w-3
              [&::-moz-range-thumb]:h-3
              [&::-moz-range-thumb]:rounded-full
              [&::-moz-range-thumb]:bg-amber-400
              [&::-moz-range-thumb]:border-2
              [&::-moz-range-thumb]:border-amber-500
              [&::-moz-range-thumb]:cursor-pointer
              [&::-moz-range-track]:bg-transparent
              [&::-webkit-slider-runnable-track]:bg-transparent"
          />
        </div>
        <span className="text-[10px] text-slate-500 whitespace-nowrap">Now</span>
      </div>
    </div>
  );
}

// Backward-compatible alias
export const SpoofingTimeControls = GnssTimeBar;
