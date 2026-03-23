import type { OwnershipData, ManualEnrichment } from '../../types/api';
import { CollapsibleSection } from './CollapsibleSection';

interface OwnershipSectionProps {
  ownershipData?: OwnershipData;
  manualEnrichment?: ManualEnrichment;
}

export function OwnershipSection({ ownershipData, manualEnrichment }: OwnershipSectionProps) {
  const hasManagement = ownershipData?.managementEntries && ownershipData.managementEntries.length > 0;
  const hasFlat = ownershipData && (
    ownershipData.registeredOwner ||
    ownershipData.commercialManager ||
    ownershipData.ismManager ||
    ownershipData.beneficialOwner
  );
  const hasIacs = ownershipData?.iacsClass;
  const hasEnrichment = manualEnrichment && (
    manualEnrichment.ownershipChain || manualEnrichment.notes
  );

  const hasAnyData = hasManagement || hasFlat || hasIacs || hasEnrichment;

  return (
    <CollapsibleSection title="Ownership" testId="ownership-section">
      {!hasAnyData ? (
        <div className="text-xs text-gray-500" data-testid="ownership-empty">
          No ownership data — enrich this vessel
        </div>
      ) : (
        <div className="space-y-3">
          {/* IACS Classification */}
          {hasIacs && (
            <div className="text-xs" data-testid="iacs-class">
              <div className="text-gray-500 font-medium mb-1">Classification (IACS)</div>
              <div className="text-gray-400 space-y-0.5">
                <div>Class: <span className="text-gray-300">{ownershipData!.iacsClass!.classSociety}</span>
                  {ownershipData!.iacsClass!.status && (
                    <span className={`ml-1.5 text-[0.65rem] px-1 py-0.5 rounded ${
                      ownershipData!.iacsClass!.status === 'Delivered' ? 'bg-green-900/40 text-green-400' :
                      ownershipData!.iacsClass!.status === 'Withdrawn' ? 'bg-red-900/40 text-red-400' :
                      ownershipData!.iacsClass!.status === 'Suspended' ? 'bg-yellow-900/40 text-yellow-400' :
                      'bg-gray-800 text-gray-400'
                    }`}>{ownershipData!.iacsClass!.status}</span>
                  )}
                </div>
                {ownershipData!.iacsClass!.dateOfSurvey && (
                  <div>Last survey: <span className="text-gray-300">{ownershipData!.iacsClass!.dateOfSurvey}</span></div>
                )}
                {ownershipData!.iacsClass!.dateOfNextSurvey && (
                  <div>Next survey: <span className="text-gray-300">{ownershipData!.iacsClass!.dateOfNextSurvey}</span></div>
                )}
              </div>
            </div>
          )}

          {/* Structured management entries (from Equasis) */}
          {hasManagement && (
            <div className="text-xs space-y-2" data-testid="management-entries">
              {ownershipData!.managementEntries!.map((entry, i) => (
                <div key={i} className="border-l-2 border-[#1F2937] pl-2">
                  <div className="text-gray-500 font-medium">{entry.role}</div>
                  <div className="text-gray-300">{entry.companyName}</div>
                  {entry.companyImo && (
                    <div className="text-gray-500">IMO: {entry.companyImo}</div>
                  )}
                  {entry.address && (
                    <div className="text-gray-500">{entry.address}</div>
                  )}
                  {entry.dateOfEffect && (
                    <div className="text-gray-500">Since: {entry.dateOfEffect}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Flat ownership fallback (when no structured equasis data) */}
          {!hasManagement && hasFlat && (
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
