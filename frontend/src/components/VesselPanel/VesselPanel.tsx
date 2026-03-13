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
import { EnrichmentHistory } from './EnrichmentHistory';

function VesselPanel() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);
  const selectVessel = useVesselStore((s) => s.selectVessel);
  const { data: vessel, isLoading } = useVesselDetail(selectedMmsi);
  const replay = useTrackReplay(selectedMmsi);

  const isOpen = selectedMmsi !== null;

  return (
    <div
      data-testid="vessel-panel"
      className={`fixed right-0 top-12 bottom-0 w-[420px] bg-gray-900 border-l border-gray-800 overflow-y-auto transition-transform duration-300 ease-in-out z-50 ${
        isOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
      aria-hidden={!isOpen}
    >
      {/* Close button + Watch + Export */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
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
        <div data-testid="panel-skeleton" className="px-4 py-3 space-y-3">
          <div className="h-5 w-48 bg-gray-700 rounded animate-pulse" />
          <div className="h-3 w-32 bg-gray-700 rounded animate-pulse" />
          <div className="h-3 w-40 bg-gray-700 rounded animate-pulse" />
          <div className="mt-4 grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-1">
                <div className="h-2.5 w-16 bg-gray-700 rounded animate-pulse" />
                <div className="h-3.5 w-24 bg-gray-700 rounded animate-pulse" />
              </div>
            ))}
          </div>
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
          <EnrichmentHistory enrichments={vessel.manualEnrichments} />
        </>
      )}
    </div>
  );
}

export { VesselPanel };
export default VesselPanel;
