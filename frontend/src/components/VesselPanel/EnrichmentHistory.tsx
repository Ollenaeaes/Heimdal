import { useState } from 'react';
import type { ManualEnrichmentRecord } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

interface EnrichmentHistoryProps {
  enrichments?: ManualEnrichmentRecord[];
}

export function sortEnrichmentsByDate(records: ManualEnrichmentRecord[]): ManualEnrichmentRecord[] {
  return [...records].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
}

export function formatEnrichmentDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function EnrichmentHistory({ enrichments }: EnrichmentHistoryProps) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const sorted = enrichments ? sortEnrichmentsByDate(enrichments) : [];

  return (
    <CollapsibleSection
      title={`Enrichment History${sorted.length > 0 ? ` (${sorted.length})` : ''}`}
      testId="enrichment-history-section"
    >
      {sorted.length === 0 ? (
        <div className="text-xs text-gray-500" data-testid="enrichment-history-empty">
          No manual enrichment data yet.
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((record) => {
            const isExpanded = expandedIds.has(record.id);
            return (
              <div
                key={record.id}
                className="border border-[#1F2937] rounded p-2 text-sm"
                data-testid="enrichment-history-card"
              >
                <button
                  onClick={() => toggleExpand(record.id)}
                  className="flex items-center justify-between w-full text-left"
                  data-testid="enrichment-history-card-toggle"
                >
                  <div>
                    <span className="text-white font-medium">{record.source}</span>
                    <span className="text-gray-500 text-xs ml-2">
                      {formatEnrichmentDate(record.createdAt)}
                    </span>
                  </div>
                  <span className="text-gray-500 text-xs">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                </button>

                {isExpanded && (
                  <div className="mt-2 space-y-1 text-xs" data-testid="enrichment-history-card-details">
                    {record.piTier && (
                      <div>
                        <span className="text-gray-500">P&I Tier: </span>
                        <span className="text-gray-300">{record.piTier.replace(/_/g, ' ')}</span>
                      </div>
                    )}
                    {record.analystNotes && (
                      <div>
                        <span className="text-gray-500">Notes: </span>
                        <span className="text-gray-300">{record.analystNotes}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </CollapsibleSection>
  );
}
