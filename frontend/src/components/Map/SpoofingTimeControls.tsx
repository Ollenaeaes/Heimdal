import { useState, useCallback, useMemo } from 'react';

export type TimePreset = '12h' | '24h' | '3d' | '7d' | 'month';

interface SpoofingTimeControlsProps {
  visible: boolean;
  onTimeRangeChange: (start: Date, end: Date) => void;
}

const PRESET_HOURS: Record<TimePreset, number> = {
  '12h': 12,
  '24h': 24,
  '3d': 72,
  '7d': 168,
  'month': 720,
};

/** Total slider range: 30 days back from now, hourly steps. */
const SLIDER_RANGE_HOURS = 30 * 24;

export function SpoofingTimeControls({ visible, onTimeRangeChange }: SpoofingTimeControlsProps) {
  const [preset, setPreset] = useState<TimePreset>('24h');
  // Slider value: 0 = 30 days ago, SLIDER_RANGE_HOURS = now
  const [sliderValue, setSliderValue] = useState(SLIDER_RANGE_HOURS);

  const now = useMemo(() => new Date(), []);

  const handlePresetChange = useCallback((p: TimePreset) => {
    setPreset(p);
    const windowHours = PRESET_HOURS[p];
    const centerDate = new Date(now.getTime() - (SLIDER_RANGE_HOURS - sliderValue) * 3600_000);
    const halfWindow = windowHours / 2 * 3600_000;
    onTimeRangeChange(
      new Date(centerDate.getTime() - halfWindow),
      new Date(centerDate.getTime() + halfWindow),
    );
  }, [sliderValue, now, onTimeRangeChange]);

  const handleSliderChange = useCallback((value: number) => {
    setSliderValue(value);
    const windowHours = PRESET_HOURS[preset];
    const centerDate = new Date(now.getTime() - (SLIDER_RANGE_HOURS - value) * 3600_000);
    const halfWindow = windowHours / 2 * 3600_000;
    onTimeRangeChange(
      new Date(centerDate.getTime() - halfWindow),
      new Date(centerDate.getTime() + halfWindow),
    );
  }, [preset, now, onTimeRangeChange]);

  const centerDate = useMemo(() => {
    return new Date(now.getTime() - (SLIDER_RANGE_HOURS - sliderValue) * 3600_000);
  }, [sliderValue, now]);

  const windowHours = PRESET_HOURS[preset];
  const windowStart = new Date(centerDate.getTime() - windowHours / 2 * 3600_000);
  const windowEnd = new Date(centerDate.getTime() + windowHours / 2 * 3600_000);

  if (!visible) return null;

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-2">
      {/* Time window label */}
      <div className="text-[11px] text-slate-400 bg-slate-900/80 px-3 py-1 rounded-full backdrop-blur-sm">
        {formatShort(windowStart)} — {formatShort(windowEnd)}
      </div>

      {/* Preset buttons */}
      <div className="flex items-center gap-1 bg-slate-900/90 backdrop-blur-sm rounded-lg px-2 py-1.5 border border-slate-700/50">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider mr-1">Spoofing</span>
        {(Object.keys(PRESET_HOURS) as TimePreset[]).map((p) => (
          <button
            key={p}
            onClick={() => handlePresetChange(p)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              preset === p
                ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Timeline slider */}
      <div className="flex items-center gap-3 bg-slate-900/90 backdrop-blur-sm rounded-lg px-4 py-2 border border-slate-700/50 w-[500px]">
        <span className="text-[10px] text-slate-500 whitespace-nowrap">
          {formatShort(new Date(now.getTime() - SLIDER_RANGE_HOURS * 3600_000))}
        </span>
        <input
          type="range"
          min={0}
          max={SLIDER_RANGE_HOURS}
          step={1}
          value={sliderValue}
          onChange={(e) => handleSliderChange(Number(e.target.value))}
          className="flex-1 h-1.5 accent-red-500 cursor-pointer"
          style={{
            background: `linear-gradient(to right, #334155 0%, #EF4444 ${(sliderValue / SLIDER_RANGE_HOURS) * 100}%, #334155 ${(sliderValue / SLIDER_RANGE_HOURS) * 100}%)`,
          }}
        />
        <span className="text-[10px] text-slate-500 whitespace-nowrap">Now</span>
      </div>
    </div>
  );
}

function formatShort(d: Date): string {
  const month = d.toLocaleString('en', { month: 'short' });
  const day = d.getDate();
  const hours = d.getUTCHours().toString().padStart(2, '0');
  const mins = d.getUTCMinutes().toString().padStart(2, '0');
  return `${month} ${day} ${hours}:${mins}`;
}
