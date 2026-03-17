import type { OwnershipData, ManualEnrichment } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

interface OwnershipSectionProps {
  ownershipData?: OwnershipData;
  manualEnrichment?: ManualEnrichment;
}

export function OwnershipSection({ ownershipData, manualEnrichment }: OwnershipSectionProps) {
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
    <CollapsibleSection title="Ownership" testId="ownership-section">
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
    </CollapsibleSection>
  );
}
