import { useVesselStore } from '../../hooks/useVesselStore';

const RISK_COLORS: Record<string, string> = {
  green: '#27AE60',
  yellow: '#D4820C',
  red: '#C0392B',
};

const TIERS = ['green', 'yellow', 'red'] as const;

/** Compute vessel counts per risk tier from the vessels Map. */
export function computeTierCounts(
  vessels: Map<number, { riskTier: string }>
): Record<string, number> {
  const counts: Record<string, number> = { green: 0, yellow: 0, red: 0 };
  for (const v of vessels.values()) {
    if (v.riskTier in counts) {
      counts[v.riskTier]++;
    }
  }
  return counts;
}

export function RiskFilter() {
  const vessels = useVesselStore((s) => s.vessels);
  const riskTiers = useVesselStore((s) => s.filters.riskTiers);
  const setFilter = useVesselStore((s) => s.setFilter);

  const counts = computeTierCounts(vessels);

  const toggle = (tier: string) => {
    const next = new Set(riskTiers);
    if (next.has(tier)) {
      next.delete(tier);
    } else {
      next.add(tier);
    }
    setFilter({ riskTiers: next });
  };

  return (
    <div className="flex items-center gap-1" data-testid="risk-filter">
      {TIERS.map((tier) => {
        const active = riskTiers.size === 0 || riskTiers.has(tier);
        return (
          <button
            key={tier}
            type="button"
            onClick={() => toggle(tier)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium
                        transition-all border ${
                          active
                            ? 'border-gray-600 bg-gray-800/80 text-white'
                            : 'border-gray-700/50 bg-gray-900/60 text-gray-500'
                        }`}
            data-testid={`risk-toggle-${tier}`}
            aria-pressed={active}
          >
            <span
              className="w-2 h-2 rounded-full"
              style={{
                backgroundColor: RISK_COLORS[tier],
                opacity: active ? 1 : 0.3,
              }}
            />
            <span>{counts[tier]}</span>
          </button>
        );
      })}
    </div>
  );
}
