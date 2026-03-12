export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SanctionsMatch {
  source: string;
  confidence: number;
  matchedField: string;
  entityUrl?: string;
}

export interface OwnershipData {
  registeredOwner?: string;
  commercialManager?: string;
  ismManager?: string;
  beneficialOwner?: string;
}

export interface ManualEnrichment {
  ownershipChain?: string;
  notes?: string;
  enrichedAt?: string;
}

export interface ManualEnrichmentRecord {
  id: number;
  source: string;
  analystNotes?: string;
  piTier?: string;
  attachments?: Record<string, unknown>;
  createdAt: string;
}

export interface EnrichmentPayload {
  source: string;
  ownership_chain?: {
    registered_owner?: string;
    commercial_manager?: string;
    beneficial_owner?: string;
  };
  pi_insurer?: string;
  pi_insurer_tier?: 'ig_member' | 'non_ig_western' | 'russian_state' | 'unknown' | 'fraudulent' | 'none';
  classification_society?: string;
  classification_iacs?: boolean;
  psc_detentions?: number;
  psc_deficiencies?: number;
  notes?: string;
}

export interface VesselDetail {
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
  riskScore: number;
  riskTier: 'green' | 'yellow' | 'red';
  owner?: string;
  operator?: string;
  yearBuilt?: number;
  anomalies?: import('./anomaly').AnomalyEvent[];
  sanctionsMatches?: SanctionsMatch[];
  ownershipData?: OwnershipData;
  manualEnrichment?: ManualEnrichment;
  manualEnrichments?: ManualEnrichmentRecord[];
}

export interface TrackPoint {
  timestamp: string;
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
}
