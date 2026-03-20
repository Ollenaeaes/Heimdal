import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Color,
  GeoJsonDataSource,
  PolylineDashMaterialProperty,
} from 'cesium';
import { getCesiumViewer } from './cesiumViewer';

const EEZ_COLOR = Color.fromCssColorString('#60A5FA');
const TERRITORIAL_COLOR = Color.fromCssColorString('#93C5FD');

interface Props {
  showEez: boolean;
  show12nm: boolean;
}

export function MaritimeBoundariesOverlay({ showEez, show12nm }: Props) {
  const eezSourceRef = useRef<GeoJsonDataSource | null>(null);
  const nm12SourceRef = useRef<GeoJsonDataSource | null>(null);

  // Fetch EEZ boundaries
  const { data: eezData } = useQuery({
    queryKey: ['maritime-boundaries', 'eez'],
    queryFn: async () => {
      const res = await fetch('/api/maritime-zones/boundaries?zone_type=eez');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: showEez,
    staleTime: Infinity,
  });

  // Fetch 12nm boundaries
  const { data: nm12Data } = useQuery({
    queryKey: ['maritime-boundaries', '12nm'],
    queryFn: async () => {
      const res = await fetch('/api/maritime-zones/boundaries?zone_type=12nm');
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: show12nm,
    staleTime: Infinity,
  });

  // EEZ layer
  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    if (showEez && eezData && eezData.features?.length > 0) {
      const ds = new GeoJsonDataSource('eez-boundaries');
      ds.load(eezData, {
        stroke: EEZ_COLOR,
        strokeWidth: 1.5,
        fill: Color.TRANSPARENT,
        clampToGround: false,
      }).then(() => {
        if (viewer.isDestroyed()) return;
        // Apply dashed material to all polylines
        for (const entity of ds.entities.values) {
          if (entity.polyline) {
            entity.polyline.material = new PolylineDashMaterialProperty({
              color: EEZ_COLOR,
              dashLength: 16,
            });
            entity.polyline.width = 1.5 as any;
          }
        }
        viewer.dataSources.add(ds);
        eezSourceRef.current = ds;
      });
    }

    return () => {
      const v = getCesiumViewer();
      if (v && !v.isDestroyed() && eezSourceRef.current) {
        v.dataSources.remove(eezSourceRef.current, true);
      }
      eezSourceRef.current = null;
    };
  }, [showEez, eezData]);

  // 12nm layer
  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    if (show12nm && nm12Data && nm12Data.features?.length > 0) {
      const ds = new GeoJsonDataSource('12nm-boundaries');
      ds.load(nm12Data, {
        stroke: TERRITORIAL_COLOR,
        strokeWidth: 1,
        fill: Color.TRANSPARENT,
        clampToGround: false,
      }).then(() => {
        if (viewer.isDestroyed()) return;
        for (const entity of ds.entities.values) {
          if (entity.polyline) {
            entity.polyline.material = new PolylineDashMaterialProperty({
              color: TERRITORIAL_COLOR,
              dashLength: 8,
            });
            entity.polyline.width = 1 as any;
          }
        }
        viewer.dataSources.add(ds);
        nm12SourceRef.current = ds;
      });
    }

    return () => {
      const v = getCesiumViewer();
      if (v && !v.isDestroyed() && nm12SourceRef.current) {
        v.dataSources.remove(nm12SourceRef.current, true);
      }
      nm12SourceRef.current = null;
    };
  }, [show12nm, nm12Data]);

  return null;
}
