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
}

export interface TrackPoint {
  timestamp: string;
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
}
