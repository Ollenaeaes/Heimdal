import { useRef, useEffect } from 'react';
import { Viewer as ResiumViewer } from 'resium';
import { Ion, Cartesian3, type Viewer } from 'cesium';
import { VesselMarkers } from './VesselMarkers';
import { TrackTrail } from './TrackTrail';
import { GfwEventMarkers } from './GfwEventMarkers';
import { SarMarkers } from './SarMarkers';

const ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN;
if (ionToken) {
  Ion.defaultAccessToken = ionToken as string;
}

export const INITIAL_LON = 15;
export const INITIAL_LAT = 68;
export const INITIAL_ALT = 5_000_000;

/** Module-level viewer reference so other hooks can access the Cesium viewer */
let _globalViewer: Viewer | null = null;
export function getCesiumViewer(): Viewer | null {
  return _globalViewer;
}

export interface GlobeViewProps {
  showGfwEvents?: boolean;
  showSarDetections?: boolean;
}

export function GlobeView({ showGfwEvents = false, showSarDetections = false }: GlobeViewProps = {}) {
  const viewerRef = useRef<{ cesiumElement?: Viewer }>(null);

  useEffect(() => {
    const check = setInterval(() => {
      const viewer = viewerRef.current?.cesiumElement;
      if (viewer && !viewer.isDestroyed()) {
        _globalViewer = viewer;
        viewer.camera.flyTo({
          destination: Cartesian3.fromDegrees(INITIAL_LON, INITIAL_LAT, INITIAL_ALT),
          duration: 0,
        });
        clearInterval(check);
      }
    }, 100);

    return () => {
      clearInterval(check);
      _globalViewer = null;
    };
  }, []);

  return (
    <ResiumViewer
      ref={viewerRef as React.RefObject<never>}
      full
      animation={false}
      timeline={false}
      baseLayerPicker={false}
      geocoder={false}
      homeButton={false}
      sceneModePicker={false}
      navigationHelpButton={false}
      infoBox={false}
      selectionIndicator={false}
      fullscreenButton={false}
      shouldAnimate
    >
      <VesselMarkers />
      <TrackTrail />
      <GfwEventMarkers visible={showGfwEvents} />
      <SarMarkers visible={showSarDetections} />
    </ResiumViewer>
  );
}
