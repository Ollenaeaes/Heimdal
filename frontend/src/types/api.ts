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

export interface EquasisUploadSummary {
  id: number;
  upload_timestamp: string;
  edition_date: string | null;
}

export interface EquasisData {
  latest: Record<string, any>;
  upload_count: number;
  uploads: EquasisUploadSummary[];
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
  sog?: number | null;
  cog?: number | null;
  heading?: number | null;
  navStatus?: number | null;
  riskScore: number;
  riskTier: 'green' | 'yellow' | 'red' | 'blacklisted';
  networkScore?: number;
  owner?: string;
  operator?: string;
  yearBuilt?: number;
  anomalies?: import('./anomaly').AnomalyEvent[];
  sanctionsMatches?: SanctionsMatch[];
  ownershipData?: OwnershipData;
  manualEnrichment?: ManualEnrichment;
  manualEnrichments?: ManualEnrichmentRecord[];
  equasis?: EquasisData | null;
}

export interface TrackPoint {
  timestamp: string;
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
}

// SAR Detection types
export interface SarDetection {
  id: string;
  detectedAt: string;
  lat: number;
  lon: number;
  estimatedLength: number | null;
  isDark: boolean;
  matchingScore: number | null;
  fishingScore: number | null;
  matchedMmsi: number | null;
  matchedVesselName: string | null;
  satellite: string | null;
  imageUrl: string | null;
}

// GNSS Zone types
export interface GnssZone {
  id: number;
  detectedAt: string;
  expiresAt: string;
  affectedCount: number;
  geometry: { type: 'Polygon'; coordinates: number[][][] };
}

// GFW Event types
export type GfwEventType = 'ENCOUNTER' | 'LOITERING' | 'AIS_DISABLING' | 'PORT_VISIT';

export interface GfwEvent {
  id: string;
  type: GfwEventType;
  startTime: string;
  endTime: string | null;
  lat: number;
  lon: number;
  vesselMmsi: number | null;
  vesselName: string | null;
  encounterPartnerMmsi: number | null;
  encounterPartnerName: string | null;
  portName: string | null;
  durationHours: number | null;
}
