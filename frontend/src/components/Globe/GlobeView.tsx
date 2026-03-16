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
import { InfrastructureOverlay } from './InfrastructureOverlay';
import { GnssZoneOverlay } from './GnssZoneOverlay';
import { DuplicateMmsiLines } from './DuplicateMmsiLines';
import { NetworkOverlay } from './NetworkOverlay';
import { HoverDatablock } from './HoverDatablock';
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
  showInfrastructure?: boolean;
  showGnssZones?: boolean;
  showNetwork?: boolean;
}

function GlobeView({ showGfwEvents = false, showSarDetections = false, showInfrastructure = false, showGnssZones = false, showNetwork = false }: GlobeViewProps = {}) {
  const viewerRef = useRef<{ cesiumElement?: Viewer }>(null);

  useEffect(() => {
    const check = setInterval(() => {
      const viewer = viewerRef.current?.cesiumElement;
      if (viewer && !viewer.isDestroyed()) {
        setCesiumViewer(viewer);

        const { scene } = viewer;

        // Intelligence workstation aesthetic — standard satellite imagery
        // Dark sky/space for UI contrast, but map is NOT darkened
        scene.backgroundColor = Color.fromCssColorString('#0F172A');
        scene.globe.baseColor = Color.fromCssColorString('#1E293B');
        scene.globe.showGroundAtmosphere = false;
        scene.fog.enabled = true;
        scene.fog.density = 0.0001;
        scene.skyAtmosphere.brightnessShift = -0.3;
        scene.skyAtmosphere.saturationShift = -0.3;

        // No dynamic lighting — consistent look regardless of time
        scene.globe.enableLighting = false;

        // Remove default imagery and replace with standard satellite
        scene.globe.imageryLayers.removeAll();

        // Standard satellite imagery — NO colour manipulation
        // The map is ground truth: ports, coastlines, terminals visible
        IonImageryProvider.fromAssetId(2)
          .then((provider) => {
            if (!viewer.isDestroyed()) {
              const satLayer = scene.globe.imageryLayers.addImageryProvider(provider);
              // Standard satellite — no darkening, no desaturation
              satLayer.brightness = 1.0;
              satLayer.contrast = 1.0;
              satLayer.saturation = 1.0;
              satLayer.gamma = 1.0;
            }
          })
          .catch(() => {
            // No Ion token — fall back to base color
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
    <>
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
        <InfrastructureOverlay visible={showInfrastructure} />
        <DuplicateMmsiLines visible={showGnssZones} />
        <NetworkOverlay visible={showNetwork} />
      </ResiumViewer>
      <HoverDatablock />
      <GnssZoneOverlay visible={showGnssZones} />
    </>
  );
}

export { GlobeView };
export default GlobeView;
