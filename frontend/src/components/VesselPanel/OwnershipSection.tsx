import type { OwnershipData, ManualEnrichment } from '../../types/api';

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
    <div className="px-4 py-3 border-b border-gray-700" data-testid="ownership-section">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Ownership
      </h3>

      {!hasOwnership && !hasEnrichment ? (
        <div className="text-xs text-gray-500" data-testid="ownership-empty">
          No ownership data — enrich this vessel
        </div>
      ) : (
        <div className="space-y-3">
          {hasOwnership && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm" data-testid="ownership-data">
              <FieldRow label="Registered Owner" value={ownershipData!.registeredOwner} />
              <FieldRow label="Commercial Manager" value={ownershipData!.commercialManager} />
              <FieldRow label="ISM Manager" value={ownershipData!.ismManager} />
              <FieldRow label="Beneficial Owner" value={ownershipData!.beneficialOwner} />
            </div>
          )}

          {hasEnrichment && (
            <div data-testid="enrichment-data">
              {manualEnrichment!.ownershipChain && (
                <div className="mb-2">
                  <dt className="text-gray-500 text-xs">Ownership Chain</dt>
                  <dd className="text-gray-300 text-sm">{manualEnrichment!.ownershipChain}</dd>
                </div>
              )}
              {manualEnrichment!.notes && (
                <div>
                  <dt className="text-gray-500 text-xs">Notes</dt>
                  <dd className="text-gray-300 text-sm">{manualEnrichment!.notes}</dd>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FieldRow({
  label,
  value,
}: {
  label: string;
  value: string | undefined;
}) {
  return (
    <div>
      <dt className="text-gray-500 text-xs">{label}</dt>
      <dd className="text-gray-300">{value ?? '—'}</dd>
    </div>
  );
}
