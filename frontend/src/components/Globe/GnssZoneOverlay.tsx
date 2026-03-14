import { Entity, PolygonGraphics } from 'resium';
import { Cartesian3, Color, MaterialProperty } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import type { GnssZone } from '../../types/api';

export interface GnssZoneOverlayProps {
  visible: boolean;
}

/** Base color for GNSS interference zones. */
const GNSS_BASE_COLOR = '#FF4444';

/**
 * Compute opacity for a GNSS zone based on affected vessel count.
 * 3 vessels = 0.15, 10+ vessels = 0.5, linear interpolation between.
 */
export function computeGnssOpacity(affectedCount: number): number {
  if (affectedCount <= 3) return 0.15;
  if (affectedCount >= 10) return 0.5;
  // Linear interpolation between 3 and 10
  return 0.15 + ((affectedCount - 3) / (10 - 3)) * (0.5 - 0.15);
}

interface GnssFeature {
  properties: {
    id: number;
    detected_at: string;
    expires_at: string;
    affected_count: number;
    details: Record<string, unknown>;
  };
  geometry: {
    type: string;
    coordinates: number[][][];
  };
}

interface GnssGeoJson {
  type: string;
  features: GnssFeature[];
}

/**
 * Renders active GNSS interference zones as semi-transparent red-orange polygons.
 * Opacity scales with affected_count.
 */
export function GnssZoneOverlay({ visible }: GnssZoneOverlayProps) {
  const { data } = useQuery<GnssGeoJson>({
    queryKey: ['gnssZones'],
    queryFn: () => fetch('/api/gnss-zones').then((r) => r.json()),
    refetchInterval: 60_000,
    enabled: visible,
  });

  if (!visible || !data?.features) return null;

  return (
    <>
      {data.features.map((feature) => {
        const coords = feature.geometry.coordinates[0];
        if (!coords) return null;

        const hierarchy = coords.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat));
        const opacity = computeGnssOpacity(feature.properties.affected_count);
        const fillColor = Color.fromCssColorString(GNSS_BASE_COLOR).withAlpha(opacity);

        return (
          <Entity key={`gnss-zone-${feature.properties.id}`}>
            <PolygonGraphics
              hierarchy={hierarchy}
              material={fillColor as unknown as MaterialProperty}
              outline
              outlineColor={Color.fromCssColorString(GNSS_BASE_COLOR)}
              outlineWidth={2}
            />
          </Entity>
        );
      })}
    </>
  );
}
