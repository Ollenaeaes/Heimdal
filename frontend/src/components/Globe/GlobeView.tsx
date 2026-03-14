import { useRef, useEffect } from 'react';
import { Viewer as ResiumViewer } from 'resium';
import { Ion, Cartesian3, Color, IonImageryProvider, type Viewer } from 'cesium';
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

        // Globe styling — dark maritime ops aesthetic
        const { scene } = viewer;
        scene.backgroundColor = Color.fromCssColorString('#0A0E17');
        scene.globe.baseColor = Color.fromCssColorString('#0A1628');
        scene.globe.showGroundAtmosphere = true;
        scene.fog.enabled = true;
        scene.fog.density = 0.0003;
        scene.skyAtmosphere.brightnessShift = -0.4;

        // Remove default imagery layers so Bing Maps doesn't show
        scene.globe.imageryLayers.removeAll();

        // Attempt Earth at Night imagery, fall back to base color on failure
        IonImageryProvider.fromAssetId(3812)
          .then((provider) => {
            if (!viewer.isDestroyed()) {
              scene.globe.imageryLayers.addImageryProvider(provider);
            }
          })
          .catch(() => {
            // Fallback: globe base color (#0A1628) is already set, nothing else needed
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
