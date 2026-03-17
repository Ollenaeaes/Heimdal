import type { SanctionsMatch } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

interface SanctionsSectionProps {
  matches?: SanctionsMatch[];
}

export function SanctionsSection({ matches }: SanctionsSectionProps) {
  const count = matches?.length ?? 0;

  return (
    <CollapsibleSection
      title={`Sanctions${count > 0 ? ` (${count})` : ''}`}
      testId="sanctions-section"
    >
      {!matches || matches.length === 0 ? (
        <div className="text-xs text-gray-500" data-testid="sanctions-empty">
          No sanctions matches found
        </div>
      ) : (
        <div className="space-y-2">
          {matches.map((match, idx) => (
            <div
              key={`${match.source}-${match.matchedField}-${idx}`}
              className="border border-[#1F2937] rounded p-2 text-sm"
              data-testid="sanctions-match"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-white font-medium">{match.source}</span>
                <span className="text-xs text-amber-400 font-mono">
                  {Math.round(match.confidence * 100)}%
                </span>
              </div>
              <div className="text-xs text-gray-400">
                Matched field: <span className="text-gray-300">{match.matchedField}</span>
              </div>
              {match.entityUrl && (
                <a
                  href={match.entityUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-400 hover:text-blue-300 mt-1 inline-block"
                  data-testid="sanctions-link"
                >
                  View on OpenSanctions
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </CollapsibleSection>
  );
}
