import { useState, useCallback } from 'react';
import type { VesselDetail, TrackPoint, GfwEvent } from '../../types/api';

interface DossierExportProps {
  vessel: VesselDetail;
}

export interface DossierData {
  exportedAt: string;
  vessel: {
    mmsi: number;
    imo?: number;
    name?: string;
    shipType?: number;
    shipTypeText?: string;
    flagCountry?: string;
    callSign?: string;
    length?: number;
    width?: number;
    draught?: number;
    destination?: string;
    owner?: string;
    operator?: string;
    yearBuilt?: number;
  };
  riskAssessment: {
    riskScore: number;
    riskTier: string;
    anomalies: VesselDetail['anomalies'];
  };
  sanctions: VesselDetail['sanctionsMatches'];
  ownership: VesselDetail['ownershipData'];
  enrichment: {
    manual?: VesselDetail['manualEnrichment'];
    history?: VesselDetail['manualEnrichments'];
  };
  gfwEvents: GfwEvent[];
  recentTrack: TrackPoint[];
}

async function fetchTrackForExport(mmsi: number): Promise<TrackPoint[]> {
  try {
    const res = await fetch(`/api/vessels/${mmsi}/track`);
    if (!res.ok) return [];
    return (await res.json()) as TrackPoint[];
  } catch {
    return [];
  }
}

async function fetchGfwEventsForExport(mmsi: number): Promise<GfwEvent[]> {
  try {
    const res = await fetch(`/api/gfw/events?mmsi=${mmsi}`);
    if (!res.ok) return [];
    return (await res.json()) as GfwEvent[];
  } catch {
    return [];
  }
}

export function buildDossier(
  vessel: VesselDetail,
  track: TrackPoint[],
  gfwEvents: GfwEvent[]
): DossierData {
  return {
    exportedAt: new Date().toISOString(),
    vessel: {
      mmsi: vessel.mmsi,
      imo: vessel.imo,
      name: vessel.name,
      shipType: vessel.shipType,
      shipTypeText: vessel.shipTypeText,
      flagCountry: vessel.flagCountry,
      callSign: vessel.callSign,
      length: vessel.length,
      width: vessel.width,
      draught: vessel.draught,
      destination: vessel.destination,
      owner: vessel.owner,
      operator: vessel.operator,
      yearBuilt: vessel.yearBuilt,
    },
    riskAssessment: {
      riskScore: vessel.riskScore,
      riskTier: vessel.riskTier,
      anomalies: vessel.anomalies ?? [],
    },
    sanctions: vessel.sanctionsMatches ?? [],
    ownership: vessel.ownershipData ?? {},
    enrichment: {
      manual: vessel.manualEnrichment,
      history: vessel.manualEnrichments ?? [],
    },
    gfwEvents,
    recentTrack: track,
  };
}

export function buildFilename(mmsi: number): string {
  const date = new Date();
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `heimdal-dossier-${mmsi}-${y}-${m}-${d}.json`;
}

export function triggerDownload(json: string, filename: string): void {
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function DossierExport({ vessel }: DossierExportProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const [track, gfwEvents] = await Promise.all([
        fetchTrackForExport(vessel.mmsi),
        fetchGfwEventsForExport(vessel.mmsi),
      ]);

      const dossier = buildDossier(vessel, track, gfwEvents);
      const json = JSON.stringify(dossier, null, 2);
      const filename = buildFilename(vessel.mmsi);
      triggerDownload(json, filename);
    } finally {
      setExporting(false);
    }
  }, [vessel]);

  return (
    <button
      data-testid="dossier-export"
      onClick={handleExport}
      disabled={exporting}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white transition-colors disabled:opacity-50"
      aria-label="Export vessel dossier"
    >
      {exporting ? (
        <>
          <span className="animate-spin">&#8635;</span>
          Exporting...
        </>
      ) : (
        <>
          <span>&#8615;</span>
          Export
        </>
      )}
    </button>
  );
}
