import { useEffect, useRef } from 'react';
import { Color, HeatmapVisualizerCompat } from 'cesium';
import { useQuery } from '@tanstack/react-query';
import { getCesiumViewer } from './cesiumViewer';

export interface GnssZoneOverlayProps {
  visible: boolean;
}

/** Base color for GNSS interference zones. */
const GNSS_BASE_COLOR = '#FF4444';

export function computeGnssOpacity(affectedCount: number): number {
  if (affectedCount <= 3) return 0.15;
  if (affectedCount >= 10) return 0.5;
  return 0.15 + ((affectedCount - 3) / (10 - 3)) * (0.5 - 0.15);
}

interface SpoofingPoint {
  lat: number;
  lon: number;
  mmsi: number;
  rule: string;
  severity: string;
  ship_name: string | null;
  time: string | null;
}

/**
 * Renders GNSS spoofing events as colored point markers on the globe.
 * Points are colored by severity and clustered visually.
 */
export function GnssZoneOverlay({ visible }: GnssZoneOverlayProps) {
  const entitiesRef = useRef<any[]>([]);

  const { data } = useQuery<{ points: SpoofingPoint[]; count: number }>({
    queryKey: ['gnssSpoofingEvents'],
    queryFn: () => fetch('/api/gnss-spoofing-events').then((r) => r.json()),
    refetchInterval: 60_000,
    enabled: visible,
  });

  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    // Clean up previous entities
    for (const entity of entitiesRef.current) {
      viewer.entities.remove(entity);
    }
    entitiesRef.current = [];

    if (!visible || !data?.points?.length) return;

    const { Cartesian3, Entity, PointGraphics: _PG } = require('cesium');

    for (const pt of data.points) {
      const color = pt.severity === 'critical'
        ? Color.fromCssColorString('#EF4444').withAlpha(0.7)
        : pt.severity === 'high'
        ? Color.fromCssColorString('#F97316').withAlpha(0.6)
        : Color.fromCssColorString('#EAB308').withAlpha(0.5);

      const entity = viewer.entities.add({
        position: Cartesian3.fromDegrees(pt.lon, pt.lat),
        point: {
          pixelSize: 8,
          color,
          outlineColor: Color.fromCssColorString('#FF4444').withAlpha(0.3),
          outlineWidth: 4,
        },
        name: `spoofing-${pt.mmsi}`,
        description: `<b>Spoofing Event</b><br/>`
          + `Vessel: ${pt.ship_name?.trim() || `MMSI ${pt.mmsi}`}<br/>`
          + `Rule: ${pt.rule.replace(/_/g, ' ')}<br/>`
          + `Severity: ${pt.severity}<br/>`
          + (pt.time ? `Time: ${new Date(pt.time).toUTCString()}` : ''),
      });
      entitiesRef.current.push(entity);
    }

    return () => {
      if (viewer && !viewer.isDestroyed()) {
        for (const entity of entitiesRef.current) {
          viewer.entities.remove(entity);
        }
        entitiesRef.current = [];
      }
    };
  }, [visible, data]);

  return null;
}
