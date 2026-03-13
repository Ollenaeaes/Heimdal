import { useEffect, useRef } from 'react';
import {
  Cartesian3,
  Color,
  LabelStyle,
  VerticalOrigin,
  Cartesian2,
  PolylineDashMaterialProperty,
  Entity,
} from 'cesium';
import { getCesiumViewer } from '../components/Globe/GlobeView';
import type { OverlayToggleState } from '../components/Globe/Overlays';
import stsZonesData from '../data/stsZones.json';
import terminalsData from '../data/terminals.json';
import eezData from '../data/eezBoundaries.json';

/** STS zone fill color: semi-transparent amber */
const STS_FILL = Color.fromCssColorString('rgba(212, 130, 12, 0.15)');
const STS_OUTLINE = Color.fromCssColorString('#D4820C');
const TERMINAL_COLOR = Color.fromCssColorString('#C0392B');
const EEZ_COLOR = Color.BLUE;

function polygonCentroid(coords: number[][]): Cartesian3 {
  const ring = coords.slice(0, -1);
  const avgLon = ring.reduce((s, c) => s + c[0], 0) / ring.length;
  const avgLat = ring.reduce((s, c) => s + c[1], 0) / ring.length;
  return Cartesian3.fromDegrees(avgLon, avgLat);
}

/**
 * Imperatively manages overlay entities on the raw Cesium Viewer.
 * Adds/removes entities as toggle state changes.
 */
export function useOverlays(overlays: OverlayToggleState) {
  const stsEntities = useRef<Entity[]>([]);
  const terminalEntities = useRef<Entity[]>([]);
  const eezEntities = useRef<Entity[]>([]);

  // STS Zones
  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    if (overlays.showStsZones) {
      for (const feature of stsZonesData.features) {
        const coords = feature.geometry.coordinates[0];
        const hierarchy = coords.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat));
        const labelPos = polygonCentroid(coords);

        const entity = viewer.entities.add({
          position: labelPos,
          polygon: {
            hierarchy: hierarchy,
            material: STS_FILL,
            outline: true,
            outlineColor: STS_OUTLINE,
            outlineWidth: 2,
          },
          label: {
            text: feature.properties.name,
            font: '12px sans-serif',
            fillColor: STS_OUTLINE,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian2(0, -10),
          },
        });
        stsEntities.current.push(entity);
      }
    }

    return () => {
      const v = getCesiumViewer();
      if (v && !v.isDestroyed()) {
        for (const e of stsEntities.current) {
          v.entities.remove(e);
        }
      }
      stsEntities.current = [];
    };
  }, [overlays.showStsZones]);

  // Russian Terminals
  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    if (overlays.showTerminals) {
      for (const feature of terminalsData.features) {
        const [lon, lat] = feature.geometry.coordinates;
        const position = Cartesian3.fromDegrees(lon, lat);

        const entity = viewer.entities.add({
          position,
          point: {
            pixelSize: 16,
            color: TERMINAL_COLOR,
            outlineColor: Color.WHITE,
            outlineWidth: 1,
          },
          label: {
            text: feature.properties.name,
            font: '12px sans-serif',
            fillColor: Color.WHITE,
            style: LabelStyle.FILL_AND_OUTLINE,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            verticalOrigin: VerticalOrigin.BOTTOM,
            pixelOffset: new Cartesian2(0, -14),
          },
        });
        terminalEntities.current.push(entity);
      }
    }

    return () => {
      const v = getCesiumViewer();
      if (v && !v.isDestroyed()) {
        for (const e of terminalEntities.current) {
          v.entities.remove(e);
        }
      }
      terminalEntities.current = [];
    };
  }, [overlays.showTerminals]);

  // Norwegian EEZ
  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    if (overlays.showEez) {
      for (const feature of eezData.features) {
        const positions = feature.geometry.coordinates.map(([lon, lat]) =>
          Cartesian3.fromDegrees(lon, lat),
        );

        const entity = viewer.entities.add({
          polyline: {
            positions,
            width: 2,
            material: new PolylineDashMaterialProperty({
              color: EEZ_COLOR,
              dashLength: 16,
            }),
          },
        });
        eezEntities.current.push(entity);
      }
    }

    return () => {
      const v = getCesiumViewer();
      if (v && !v.isDestroyed()) {
        for (const e of eezEntities.current) {
          v.entities.remove(e);
        }
      }
      eezEntities.current = [];
    };
  }, [overlays.showEez]);
}
