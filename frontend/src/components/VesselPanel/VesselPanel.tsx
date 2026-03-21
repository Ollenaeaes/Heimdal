import { useState } from 'react';
import { useVesselStore } from '../../hooks/useVesselStore';
import { useVesselDetail } from '../../hooks/useVesselDetail';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { WatchButton } from './WatchButton';
import { DossierExport } from './DossierExport';
import { IdentitySection } from './IdentitySection';
import { StatusSection } from './StatusSection';
import { RiskSection } from './RiskSection';
import { VoyageTimeline } from './VoyageTimeline';
import { LookbackSection } from './LookbackSection';
import { TrackExportSection } from './TrackExportSection';
import { SanctionsSection } from './SanctionsSection';
import { OwnershipSection } from './OwnershipSection';
import { NetworkGraph } from './NetworkGraph';
import { VesselChain } from './VesselChain';
import { EnrichmentForm } from './EnrichmentForm';
import { EquasisUpload } from './EquasisUpload';
import { EnrichmentHistory } from './EnrichmentHistory';
import { EquasisSection } from './EquasisSection';

type GroupKey = 'risk' | 'voyage' | 'enrichment';

function GroupHeader({
  label,
  groupKey,
  open,
  onToggle,
}: {
  label: string;
  groupKey: GroupKey;
  open: boolean;
  onToggle: (key: GroupKey) => void;
}) {
  return (
    <button
      onClick={() => onToggle(groupKey)}
      className="flex items-center justify-between w-full px-3 py-1.5 text-[0.65rem] font-medium uppercase tracking-wider text-slate-500 hover:text-slate-300 bg-[#0D1321] border-y border-[#1F2937] transition-colors"
    >
      {label}
      <span className="text-[0.6rem]">{open ? '▾' : '▸'}</span>
    </button>
  );
}

function VesselPanel() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const { data: vessel, isLoading } = useVesselDetail(selectedMmsi);
  const deactivateLookback = useLookbackStore((s) => s.deactivate);

  const [openGroups, setOpenGroups] = useState<Record<GroupKey, boolean>>({
    risk: true,
    voyage: false,
    enrichment: false,
  });

  const toggleGroup = (key: GroupKey) => {
    setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const isOpen = selectedMmsi !== null;

  return (
    <div
      data-testid="vessel-panel"
      className={`fixed right-0 top-10 bottom-0 w-[420px] bg-[#111827] border-l border-[#1F2937] rounded-none overflow-y-auto transition-transform duration-300 ease-in-out z-50 ${
        isOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
      aria-hidden={!isOpen}
    >
      {/* Close button + Watch + Export */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#1F2937]">
        <div className="flex items-center gap-2">
          {selectedMmsi !== null ? (
            <>
              <WatchButton mmsi={selectedMmsi} />
              {vessel && <DossierExport vessel={vessel} />}
            </>
          ) : (
            <span />
          )}
        </div>
        <button
          data-testid="panel-close"
          onClick={() => {
            deactivateLookback();
            selectVessel(null);
          }}
          className="text-gray-400 hover:text-white text-lg leading-none"
          aria-label="Close panel"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      {isLoading && (
        <div data-testid="panel-skeleton" className="px-3 py-2">
          <span className="text-sm text-gray-500">Loading vessel...</span>
        </div>
      )}

      {vessel && !isLoading && (
        <>
          {/* Identity & Status — always visible */}
          <IdentitySection vessel={vessel} />
          <StatusSection vessel={vessel} mmsi={vessel.mmsi} />

          {/* Risk & Intelligence */}
          <GroupHeader label="Risk & Intelligence" groupKey="risk" open={openGroups.risk} onToggle={toggleGroup} />
          {openGroups.risk && (
            <>
              <RiskSection vessel={vessel} />
              <SanctionsSection matches={vessel.sanctionsMatches} />
              <OwnershipSection
                ownershipData={vessel.ownershipData}
                manualEnrichment={vessel.manualEnrichment}
              />
              <NetworkGraph mmsi={vessel.mmsi} />
              <VesselChain mmsi={vessel.mmsi} />
            </>
          )}

          {/* Voyage & Track */}
          <GroupHeader label="Voyage & Track" groupKey="voyage" open={openGroups.voyage} onToggle={toggleGroup} />
          {openGroups.voyage && (
            <>
              <VoyageTimeline mmsi={vessel.mmsi} anomalies={vessel.anomalies ?? []} />
              <LookbackSection mmsi={vessel.mmsi} />
              <TrackExportSection mmsi={vessel.mmsi} />
            </>
          )}

          {/* Enrichment & Data */}
          <GroupHeader label="Enrichment & Data" groupKey="enrichment" open={openGroups.enrichment} onToggle={toggleGroup} />
          {openGroups.enrichment && (
            <>
              <EnrichmentForm mmsi={vessel.mmsi} />
              <EquasisSection mmsi={vessel.mmsi} equasis={vessel.equasis} />
              <EquasisUpload mmsi={vessel.mmsi} />
              <EnrichmentHistory enrichments={vessel.manualEnrichments} />
            </>
          )}
        </>
      )}
    </div>
  );
}

export { VesselPanel };
export default VesselPanel;
