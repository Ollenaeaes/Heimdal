import { useCallback, useState } from 'react';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapRef, MapLayerMouseEvent } from 'react-map-gl/maplibre';
import { setMapInstance, INITIAL_CENTER, INITIAL_ZOOM } from './mapInstance';
import { createMapStyle } from './style';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { useVesselStore } from '../../hooks/useVesselStore';
import { VesselLayer } from './VesselLayer';
import { StaticOverlays } from './StaticOverlays';
import { InfrastructureLayer } from './InfrastructureLayer';
import { GnssHeatmap } from './GnssHeatmap';
import { PlaybackGnssOverlay } from './PlaybackGnssOverlay';
import { GnssTimeBar } from './SpoofingTimeControls';
import { GnssLegend } from './GnssLegend';
import { DuplicateMmsiLayer } from './DuplicateMmsiLayer';
import { NetworkLayer } from './NetworkLayer';
import { GfwEventLayer } from './GfwEventLayer';
import { SarDetectionLayer } from './SarDetectionLayer';
import { TrackTrails } from './TrackTrails';
import { TrackTrail } from './TrackTrail';
import { HoverTooltip } from './HoverTooltip';
import { LookbackLayer } from './LookbackLayer';
import { AreaDrawingTool } from './AreaDrawingTool';
import { TimelineBar } from './TimelineBar';
import { useLookbackTracks } from '../../hooks/useLookbackTracks';

export interface MapViewProps {
  showGfwEvents?: boolean;
  showSarDetections?: boolean;
  showInfrastructure?: boolean;
  showGnssZones?: boolean;
  showNetwork?: boolean;
  showStsZones?: boolean;
  showTerminals?: boolean;
  showSeaBorders?: boolean;
  showSeaBordersEez?: boolean;
  showSeaBorders12nm?: boolean;
}

const mapStyle = createMapStyle();

const VESSEL_LAYER_IDS = ['vessel-dots-stationary', 'vessel-arrows', 'vessel-hulls'];

function MapView(props: MapViewProps) {
  const lookbackActive = useLookbackStore((s) => s.isActive);
  const selectVessel = useVesselStore((s) => s.selectVessel);

  // GNSS heatmap time state — shared between GnssHeatmap and GnssTimeBar
  const [gnssCenterTime, setGnssCenterTime] = useState(() => new Date());
  const [gnssWindowSize, setGnssWindowSize] = useState('24h');

  // Fetch tracks when lookback activates
  useLookbackTracks();

  const onLoad = useCallback((evt: { target: maplibregl.Map }) => {
    setMapInstance(evt.target);
  }, []);

  const mapRef = useCallback((ref: MapRef | null) => {
    if (!ref) {
      setMapInstance(null);
    }
  }, []);

  const onClick = useCallback((e: MapLayerMouseEvent) => {
    if (!e.features?.length) return;
    const feature = e.features[0];
    const layerId = feature.layer?.id;
    if (!layerId || !VESSEL_LAYER_IDS.includes(layerId)) return;

    const mmsi = feature.properties?.mmsi;
    if (mmsi == null) return;

    selectVessel(Number(mmsi));
  }, [selectVessel]);

  const showGnssOverlay = useLookbackStore((s) => s.showGnssOverlay);
  const legendVisible = (props.showGnssZones ?? false) || (lookbackActive && showGnssOverlay);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
    <GnssLegend visible={legendVisible} />
    <Map
      ref={mapRef}
      initialViewState={{
        longitude: INITIAL_CENTER[0],
        latitude: INITIAL_CENTER[1],
        zoom: INITIAL_ZOOM,
      }}
      style={{ width: '100%', height: '100%' }}
      mapStyle={mapStyle}
      onLoad={onLoad}
      onClick={onClick}
      interactiveLayerIds={VESSEL_LAYER_IDS}
    >
      <StaticOverlays
        showStsZones={props.showStsZones ?? false}
        showTerminals={props.showTerminals ?? false}
        showSeaBorders={props.showSeaBorders ?? false}
        showSeaBordersEez={props.showSeaBordersEez ?? false}
        showSeaBorders12nm={props.showSeaBorders12nm ?? false}
      />
      <InfrastructureLayer visible={props.showInfrastructure ?? false} />
      {!lookbackActive && <VesselLayer />}
      {!lookbackActive && <TrackTrails />}
      {!lookbackActive && <TrackTrail />}
      <GnssHeatmap visible={props.showGnssZones ?? false} centerTime={gnssCenterTime} windowSize={gnssWindowSize} />
      <PlaybackGnssOverlay />
      <DuplicateMmsiLayer visible={props.showGnssZones ?? false} />
      <NetworkLayer visible={props.showNetwork ?? false} />
      <GfwEventLayer visible={props.showGfwEvents ?? false} />
      <SarDetectionLayer visible={props.showSarDetections ?? false} />
      <LookbackLayer />
      <AreaDrawingTool />
      <HoverTooltip />
      {lookbackActive && <TimelineBar />}
      <GnssTimeBar
        visible={props.showGnssZones ?? false}
        centerTime={gnssCenterTime}
        windowSize={gnssWindowSize}
        onCenterTimeChange={setGnssCenterTime}
        onWindowSizeChange={setGnssWindowSize}
      />
    </Map>
    </div>
  );
}

export { MapView };
export default MapView;
