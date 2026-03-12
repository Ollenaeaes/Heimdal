export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
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
}

export interface TrackPoint {
  timestamp: string;
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
}
