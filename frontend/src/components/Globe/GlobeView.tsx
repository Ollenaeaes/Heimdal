import { useRef, useEffect } from 'react';
import { Viewer as ResiumViewer } from 'resium';
import {
  Ion,
  Cartesian3,
  Color,
  IonImageryProvider,
  type Viewer,
} from 'cesium';
import { VesselMarkers } from './VesselMarkers';
import { TrackTrail } from './TrackTrail';
import { GfwEventMarkers } from './GfwEventMarkers';
import { SarMarkers } from './SarMarkers';
import { INITIAL_LON, INITIAL_LAT, INITIAL_ALT, setCesiumViewer } from './cesiumViewer';

const ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN;
if (ionToken) {
  Ion.defaultAccessToken = ionToken as string;
}

// Re-export constants and getCesiumViewer for backward compatibility
export { INITIAL_LON, INITIAL_LAT, INITIAL_ALT } from './cesiumViewer';
export { getCesiumViewer } from './cesiumViewer';

export interface GlobeViewProps {
  showGfwEvents?: boolean;
  showSarDetections?: boolean;
}

function GlobeView({ showGfwEvents = false, showSarDetections = false }: GlobeViewProps = {}) {
  const viewerRef = useRef<{ cesiumElement?: Viewer }>(null);

  useEffect(() => {
    const check = setInterval(() => {
      const viewer = viewerRef.current?.cesiumElement;
      if (viewer && !viewer.isDestroyed()) {
        setCesiumViewer(viewer);

        const { scene } = viewer;

        // Dark ops-centre aesthetic — dark sky/space but real satellite terrain
        scene.backgroundColor = Color.fromCssColorString('#070B12');
        scene.globe.baseColor = Color.fromCssColorString('#0B1120');
        scene.globe.showGroundAtmosphere = false;
        scene.fog.enabled = true;
        scene.fog.density = 0.0001;
        scene.skyAtmosphere.brightnessShift = -0.5;
        scene.skyAtmosphere.saturationShift = -0.5;

        // No dynamic lighting — consistent look regardless of time
        scene.globe.enableLighting = false;

        // Remove default imagery and replace with satellite
        scene.globe.imageryLayers.removeAll();

        // Satellite imagery base — real terrain, coastlines, ports visible
        IonImageryProvider.fromAssetId(2)
          .then((provider) => {
            if (!viewer.isDestroyed()) {
              const satLayer = scene.globe.imageryLayers.addImageryProvider(provider);
              // Darken & desaturate for military ops-centre look
              // Terrain stays visible but muted — CMO-style
              satLayer.brightness = 0.55;
              satLayer.contrast = 1.3;
              satLayer.saturation = 0.35;
              satLayer.gamma = 0.9;
            }
          })
          .catch(() => {
            // No Ion token — fall back to dark base color
          });

        viewer.camera.flyTo({
          destination: Cartesian3.fromDegrees(INITIAL_LON, INITIAL_LAT, INITIAL_ALT),
          duration: 0,
        });
        clearInterval(check);
      }
    }, 100);

    return () => {
      clearInterval(check);
      setCesiumViewer(null);
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

export { GlobeView };
export default GlobeView;
