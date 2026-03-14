import { useRef, useEffect } from 'react';
import { Viewer as ResiumViewer } from 'resium';
import {
  Ion,
  Cartesian3,
  Color,
  IonImageryProvider,
  UrlTemplateImageryProvider,
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

        // Dark maritime ops aesthetic
        scene.backgroundColor = Color.fromCssColorString('#0A0E17');
        scene.globe.baseColor = Color.fromCssColorString('#0B1120');
        scene.globe.showGroundAtmosphere = true;
        scene.fog.enabled = true;
        scene.fog.density = 0.00025;
        scene.skyAtmosphere.brightnessShift = -0.3;

        // Enable lighting for subtle land/sea shading
        scene.globe.enableLighting = false;

        // Remove default imagery
        scene.globe.imageryLayers.removeAll();

        // Use CartoDB dark matter tiles — dark basemap with visible coastlines & land contrast
        const darkTiles = new UrlTemplateImageryProvider({
          url: 'https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png',
          credit: '© CARTO © OpenStreetMap contributors',
          minimumLevel: 0,
          maximumLevel: 18,
        });
        scene.globe.imageryLayers.addImageryProvider(darkTiles);

        // Try Earth at Night on top (semi-transparent) for city glow, fallback silently
        IonImageryProvider.fromAssetId(3812)
          .then((provider) => {
            if (!viewer.isDestroyed()) {
              const nightLayer = scene.globe.imageryLayers.addImageryProvider(provider);
              nightLayer.alpha = 0.3; // subtle city lights overlay
            }
          })
          .catch(() => {
            // No Ion token or asset unavailable — dark tiles alone are fine
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
