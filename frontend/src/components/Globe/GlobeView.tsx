import { useState } from 'react';
import { Viewer, CameraFlyTo } from 'resium';
import { Ion, Cartesian3 } from 'cesium';
import { useWebSocket } from '../../hooks/useWebSocket';
import { VesselCluster } from './VesselCluster';
import { TrackTrails } from './TrackTrails';
import { ReplayOverlay } from './ReplayOverlay';
import { Overlays, OverlayToggles } from './Overlays';
import { SarMarkers } from './SarMarkers';
import { GfwEventMarkers } from './GfwEventMarkers';
import type { OverlayToggleState } from './Overlays';
import { useReplayStore } from '../../hooks/useReplayStore';

// Set Cesium Ion token if available
const ionToken = import.meta.env.VITE_CESIUM_ION_TOKEN;
if (ionToken) {
  Ion.defaultAccessToken = ionToken as string;
}

/** Initial camera: Norwegian EEZ — lat 68, lon 15, altitude 5 000 km */
export const INITIAL_LON = 15;
export const INITIAL_LAT = 68;
export const INITIAL_ALT = 5_000_000;

const initialPosition = Cartesian3.fromDegrees(INITIAL_LON, INITIAL_LAT, INITIAL_ALT);

export function GlobeView() {
  // Establish WebSocket connection on mount
  useWebSocket();

  const replayState = useReplayStore();
  const [trackTrailsEnabled] = useState(true);
  const [overlayState, setOverlayState] = useState<OverlayToggleState>({
    showStsZones: false,
    showTerminals: false,
    showEez: false,
    showSarDetections: false,
    showGfwEvents: false,
  });

  return (
    <>
      <Viewer
        full
        shouldAnimate
        infoBox={false}
        selectionIndicator={false}
        homeButton={false}
        baseLayerPicker={false}
        navigationHelpButton={false}
        animation={false}
        timeline={false}
        fullscreenButton={false}
        geocoder={false}
        sceneModePicker={false}
      >
        <CameraFlyTo destination={initialPosition} duration={0} />
        <VesselCluster />
        <TrackTrails enabled={trackTrailsEnabled} />
        <Overlays
          showStsZones={overlayState.showStsZones}
          showTerminals={overlayState.showTerminals}
          showEez={overlayState.showEez}
        />
        <SarMarkers visible={overlayState.showSarDetections} />
        <GfwEventMarkers visible={overlayState.showGfwEvents} />
        <ReplayOverlay replay={replayState} />
      </Viewer>
      {/* Overlay toggle controls */}
      <div className="absolute bottom-4 left-4 z-10">
        <OverlayToggles state={overlayState} onChange={setOverlayState} />
      </div>
    </>
  );
}
