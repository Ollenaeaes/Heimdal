import { useVesselStore } from '../../hooks/useVesselStore';

/** Predefined ship type filter presets. */
const TYPE_PRESETS: { label: string; codes: number[] }[] = [
  { label: 'All Types', codes: [] },
  { label: 'Tankers (80-89)', codes: Array.from({ length: 10 }, (_, i) => 80 + i) },
  { label: 'Cargo (70-79)', codes: Array.from({ length: 10 }, (_, i) => 70 + i) },
  { label: 'Passenger (60-69)', codes: Array.from({ length: 10 }, (_, i) => 60 + i) },
];

export function TypeFilter() {
  const shipTypes = useVesselStore((s) => s.filters.shipTypes);
  const setFilter = useVesselStore((s) => s.setFilter);

  /** Find the matching preset, or "custom" if none match */
  const currentValue = (): string => {
    if (shipTypes.length === 0) return 'all';
    const preset = TYPE_PRESETS.find(
      (p) =>
        p.codes.length === shipTypes.length &&
        p.codes.every((c) => shipTypes.includes(c))
    );
    return preset ? preset.label : 'custom';
  };

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value === 'all') {
      setFilter({ shipTypes: [] });
      return;
    }
    const preset = TYPE_PRESETS.find((p) => p.label === value);
    if (preset) {
      setFilter({ shipTypes: [...preset.codes] });
    }
  };

  const selected = currentValue();

  return (
    <div data-testid="type-filter">
      <select
        value={selected === 'custom' ? 'custom' : selected === 'all' ? 'all' : TYPE_PRESETS.find((p) => p.label === selected)?.label ?? 'all'}
        onChange={handleChange}
        className="px-2.5 py-1.5 rounded text-xs font-medium bg-[#111827]/80 text-white
                   border border-[#1F2937] focus:border-[#3B82F6] focus:outline-none
                   backdrop-blur-md cursor-pointer appearance-none pr-6"
        aria-label="Filter by vessel type"
        data-testid="type-filter-select"
      >
        {TYPE_PRESETS.map((preset) => (
          <option key={preset.label} value={preset.label === 'All Types' ? 'all' : preset.label}>
            {preset.label}
          </option>
        ))}
        {selected === 'custom' && (
          <option value="custom" disabled>
            Custom
          </option>
        )}
      </select>
    </div>
  );
}
