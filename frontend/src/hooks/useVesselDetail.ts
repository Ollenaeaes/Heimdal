import { useQuery } from '@tanstack/react-query';
import type { VesselDetail } from '../types/api';

async function fetchVesselDetail(mmsi: number): Promise<VesselDetail> {
  const res = await fetch(`/api/vessels/${mmsi}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch vessel ${mmsi}: ${res.status}`);
  }
  const raw = await res.json();

  // Parse sanctions_status — stored as JSON string in DB
  let sanctionsMatches: VesselDetail['sanctionsMatches'] = [];
  if (raw.sanctions_status) {
    try {
      const parsed = typeof raw.sanctions_status === 'string'
        ? JSON.parse(raw.sanctions_status)
        : raw.sanctions_status;
      if (parsed?.matches) {
        sanctionsMatches = parsed.matches.map((m: Record<string, unknown>) => ({
          source: String(m.program ?? m.source ?? 'unknown'),
          confidence: Number(m.confidence ?? 0),
          matchedField: String(m.matched_field ?? m.matchedField ?? ''),
          entityUrl: m.entity_id
            ? `https://opensanctions.org/entities/${m.entity_id}/`
            : undefined,
        }));
      }
    } catch {
      // Ignore malformed sanctions data
    }
  }

  // Map snake_case API response to camelCase VesselDetail
  return {
    mmsi: raw.mmsi,
    imo: raw.imo ?? undefined,
    name: raw.ship_name ?? undefined,
    shipType: raw.ship_type ?? undefined,
    shipTypeText: raw.ship_type_text ?? undefined,
    flagCountry: raw.flag_country ?? undefined,
    callSign: raw.call_sign ?? undefined,
    length: raw.length ?? undefined,
    width: raw.width ?? undefined,
    draught: raw.last_position?.draught ?? raw.draught ?? undefined,
    destination: raw.destination ?? undefined,
    sog: raw.last_position?.sog ?? null,
    cog: raw.last_position?.cog ?? null,
    heading: raw.last_position?.heading ?? null,
    navStatus: raw.last_position?.nav_status ?? null,
    riskScore: raw.risk_score ?? 0,
    riskTier: raw.risk_tier ?? 'green',
    networkScore: raw.network_score ?? 0,
    owner: raw.owner ?? raw.registered_owner ?? undefined,
    operator: raw.operator ?? raw.technical_manager ?? undefined,
    yearBuilt: raw.build_year ?? undefined,
    anomalies: Array.isArray(raw.anomalies) ? raw.anomalies : [],
    sanctionsMatches,
    ownershipData: {
      registeredOwner: raw.registered_owner ?? undefined,
      commercialManager: raw.group_owner ?? undefined,
      ismManager: raw.technical_manager ?? undefined,
      beneficialOwner: raw.owner ?? undefined,
      managementEntries: (() => {
        // ownership_data is JSONB — either Equasis format (array) or GFW format (object with owners)
        const od = raw.ownership_data;
        if (!od) return undefined;
        const parsed = typeof od === 'string' ? JSON.parse(od) : od;

        // Equasis format: array of {role, company_name, company_imo, address, date_of_effect}
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed.map((e: Record<string, unknown>) => ({
            role: String(e.role ?? ''),
            companyName: String(e.company_name ?? ''),
            companyImo: e.company_imo ? String(e.company_imo) : undefined,
            address: e.address ? String(e.address) : undefined,
            dateOfEffect: e.date_of_effect ? String(e.date_of_effect) : undefined,
          }));
        }

        // GFW format: {owners: [{name, country, role, fleet_size, incorporated_date}], ...}
        if (parsed.owners && Array.isArray(parsed.owners) && parsed.owners.length > 0) {
          return parsed.owners.map((e: Record<string, unknown>) => ({
            role: String(e.role === 'owner' ? 'Registered owner' : e.role === 'operator' ? 'Operator' : e.role ?? ''),
            companyName: String(e.name ?? ''),
            companyImo: undefined,
            address: e.country ? String(e.country) : undefined,
            dateOfEffect: e.incorporated_date ? String(e.incorporated_date) : undefined,
          }));
        }

        return undefined;
      })(),
      iacsClass: raw.iacs ? {
        classSociety: raw.iacs.class_society,
        status: raw.iacs.status ?? undefined,
        dateOfSurvey: raw.iacs.date_of_survey ?? undefined,
        dateOfNextSurvey: raw.iacs.date_of_next_survey ?? undefined,
        dateOfLatestStatus: raw.iacs.date_of_latest_status ?? undefined,
        reason: raw.iacs.reason ?? undefined,
      } : undefined,
    },
    manualEnrichment: raw.latest_enrichment ?? undefined,
    manualEnrichments: [],
    lastPositionTime: raw.last_position?.timestamp ?? undefined,
  };
}

export function useVesselDetail(mmsi: number | null) {
  return useQuery<VesselDetail>({
    queryKey: ['vessel', mmsi],
    queryFn: () => fetchVesselDetail(mmsi!),
    enabled: mmsi !== null,
  });
}
