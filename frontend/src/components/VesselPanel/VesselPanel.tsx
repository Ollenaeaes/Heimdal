import { useVesselStore } from '../../hooks/useVesselStore';
import { useVesselDetail } from '../../hooks/useVesselDetail';
import { useTrackReplay } from '../../hooks/useTrackReplay';
import { WatchButton } from './WatchButton';
import { DossierExport } from './DossierExport';
import { IdentitySection } from './IdentitySection';
import { StatusSection } from './StatusSection';
import { RiskSection } from './RiskSection';
import { VoyageTimeline } from './VoyageTimeline';
import { TrackReplay } from './TrackReplay';
import { SanctionsSection } from './SanctionsSection';
import { OwnershipSection } from './OwnershipSection';
import { EnrichmentForm } from './EnrichmentForm';
import { EquasisUpload } from './EquasisUpload';
import { EnrichmentHistory } from './EnrichmentHistory';
import { EquasisSection } from './EquasisSection';

function VesselPanel() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const { data: vessel, isLoading } = useVesselDetail(selectedMmsi);
  const replay = useTrackReplay(selectedMmsi);

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
            replay.deactivate();
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
          <IdentitySection vessel={vessel} />
          <StatusSection vessel={vessel} mmsi={vessel.mmsi} />
          <RiskSection vessel={vessel} />
          <VoyageTimeline mmsi={vessel.mmsi} anomalies={vessel.anomalies ?? []} />
          <TrackReplay replay={replay} />
          <SanctionsSection matches={vessel.sanctionsMatches} />
          <OwnershipSection
            ownershipData={vessel.ownershipData}
            manualEnrichment={vessel.manualEnrichment}
          />
          <EnrichmentForm mmsi={vessel.mmsi} />
          <EquasisSection mmsi={vessel.mmsi} equasis={vessel.equasis} />
          <EquasisUpload mmsi={vessel.mmsi} />
          <EnrichmentHistory enrichments={vessel.manualEnrichments} />
        </>
      )}
    </div>
  );
}

export { VesselPanel };
export default VesselPanel;
