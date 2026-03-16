export interface VesselState {
  mmsi: number;
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
  navStatus?: number | null;
  riskTier: 'green' | 'yellow' | 'red' | 'blacklisted';
  riskScore: number;
  name?: string;
  timestamp: string; // ISO 8601
  shipType?: number;
  flagCountry?: string;
  destination?: string;
}
