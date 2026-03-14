import { useState } from 'react';
import { subHours, subDays } from 'date-fns';
import { useVesselStore } from '../../hooks/useVesselStore';

export interface TimePreset {
  label: string;
  key: string;
  getTime: () => string | null;
}

export const TIME_PRESETS: TimePreset[] = [
  { label: '1h', key: '1h', getTime: () => subHours(new Date(), 1).toISOString() },
  { label: '6h', key: '6h', getTime: () => subHours(new Date(), 6).toISOString() },
  { label: '24h', key: '24h', getTime: () => subHours(new Date(), 24).toISOString() },
  { label: '7d', key: '7d', getTime: () => subDays(new Date(), 7).toISOString() },
  { label: 'All', key: 'all', getTime: () => null },
];

export function TimeRangeFilter() {
  const [activeKey, setActiveKey] = useState<string>('all');
  const setFilter = useVesselStore((s) => s.setFilter);

  const handleClick = (preset: TimePreset) => {
    setActiveKey(preset.key);
    setFilter({ activeSince: preset.getTime() });
  };

  return (
    <div data-testid="time-range-filter" className="flex items-center gap-1">
      {TIME_PRESETS.map((preset) => (
        <button
          key={preset.key}
          data-testid={`time-preset-${preset.key}`}
          onClick={() => handleClick(preset)}
          className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
            activeKey === preset.key
              ? 'bg-[#3B82F6] text-white'
              : 'bg-[#111827] text-gray-300 hover:bg-[#1F2937] border border-[#1F2937]'
          }`}
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}
