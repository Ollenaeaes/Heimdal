import { useState } from 'react';
import type { OwnershipData, ManualEnrichment } from '../../types/api';

interface OwnershipSectionProps {
  ownershipData?: OwnershipData;
  manualEnrichment?: ManualEnrichment;
}

export function OwnershipSection({ ownershipData, manualEnrichment }: OwnershipSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const hasOwnership = ownershipData && (
    ownershipData.registeredOwner ||
    ownershipData.commercialManager ||
    ownershipData.ismManager ||
    ownershipData.beneficialOwner
  );
  const hasEnrichment = manualEnrichment && (
    manualEnrichment.ownershipChain || manualEnrichment.notes
  );

  return (
    <div className="border-b border-[#1F2937]" data-testid="ownership-section">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2"
      >
        <span className="text-xs text-gray-400 uppercase tracking-wide font-medium">Ownership</span>
        <span className="text-gray-500 text-xs">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-2">
          {!hasOwnership && !hasEnrichment ? (
            <div className="text-xs text-gray-500" data-testid="ownership-empty">
              No ownership data — enrich this vessel
            </div>
          ) : (
            <div className="space-y-2">
              {hasOwnership && (
                <div className="text-xs text-gray-400 space-y-0.5" data-testid="ownership-data">
                  {ownershipData!.registeredOwner && (
                    <div>Registered Owner: <span className="text-gray-300">{ownershipData!.registeredOwner}</span></div>
                  )}
                  {ownershipData!.commercialManager && (
                    <div>Commercial Manager: <span className="text-gray-300">{ownershipData!.commercialManager}</span></div>
                  )}
                  {ownershipData!.ismManager && (
                    <div>ISM Manager: <span className="text-gray-300">{ownershipData!.ismManager}</span></div>
                  )}
                  {ownershipData!.beneficialOwner && (
                    <div>Beneficial Owner: <span className="text-gray-300">{ownershipData!.beneficialOwner}</span></div>
                  )}
                </div>
              )}

              {hasEnrichment && (
                <div className="text-xs text-gray-400 space-y-0.5" data-testid="enrichment-data">
                  {manualEnrichment!.ownershipChain && (
                    <div>Ownership Chain: <span className="text-gray-300">{manualEnrichment!.ownershipChain}</span></div>
                  )}
                  {manualEnrichment!.notes && (
                    <div>Notes: <span className="text-gray-300">{manualEnrichment!.notes}</span></div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
