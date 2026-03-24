import { useCallback, useMemo } from 'react';

// --- Exported helpers (for testing) ---

/** Convert a real-time multiplier (60–18000) to slider position (0–100) */
export function speedToSlider(speed: number): number {
  const clamped = Math.max(60, Math.min(18000, speed));
  return (Math.log(clamped / 60) / Math.log(300)) * 100;
}

/** Convert a slider position (0–100) to real-time multiplier (60–18000) */
export function sliderToSpeed(sliderValue: number): number {
  const clamped = Math.max(0, Math.min(100, sliderValue));
  return 60 * Math.pow(300, clamped / 100);
}

/** Format a speed value as a human-readable label */
export function formatSpeedLabel(speed: number): string {
  const clamped = Math.max(60, Math.min(18000, speed));

  if (clamped >= 3600) {
    const hours = clamped / 3600;
    const rounded = Math.round(hours * 10) / 10;
    // Show integer if it's a whole number
    const display = rounded === Math.floor(rounded) ? Math.floor(rounded) : rounded;
    return `${display} hr/sec`;
  }

  const minutes = clamped / 60;
  const rounded = Math.round(minutes);
  return `${rounded} min/sec`;
}

// --- Component ---

export interface SpeedSliderProps {
  /** Real-time multiplier: 60 (1 min/sec) to 18000 (5 hr/sec) */
  value: number;
  onChange: (speed: number) => void;
  className?: string;
}

export function SpeedSlider({ value, onChange, className = '' }: SpeedSliderProps) {
  const sliderValue = useMemo(() => speedToSlider(value), [value]);
  const label = useMemo(() => formatSpeedLabel(value), [value]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const raw = Number(e.target.value);
      const speed = sliderToSpeed(raw);
      onChange(speed);
    },
    [onChange],
  );

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <input
        type="range"
        min={0}
        max={100}
        step={0.5}
        value={sliderValue}
        onChange={handleChange}
        className="w-[130px] h-1.5 appearance-none bg-slate-700 rounded cursor-pointer
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
      <span className="text-[10px] text-slate-400 whitespace-nowrap min-w-[70px]">
        {label}
      </span>
    </div>
  );
}
