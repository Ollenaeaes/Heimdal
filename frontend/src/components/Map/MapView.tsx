import { useCallback } from 'react';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapRef } from 'react-map-gl/maplibre';
import { setMapInstance, INITIAL_CENTER, INITIAL_ZOOM } from './mapInstance';
import { createMapStyle } from './style';
import { useLookbackStore } from '../../hooks/useLookbackStore';
import { VesselLayer } from './VesselLayer';
import { StaticOverlays } from './StaticOverlays';
import { InfrastructureLayer } from './InfrastructureLayer';
import { GnssHeatmap } from './GnssHeatmap';
import { DuplicateMmsiLayer } from './DuplicateMmsiLayer';
import { NetworkLayer } from './NetworkLayer';

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

function MapView(props: MapViewProps) {
  const lookbackActive = useLookbackStore((s) => s.isActive);

  const onLoad = useCallback((evt: { target: maplibregl.Map }) => {
    setMapInstance(evt.target);
  }, []);

  const mapRef = useCallback((ref: MapRef | null) => {
    if (!ref) {
      setMapInstance(null);
    }
  }, []);

  return (
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
      interactiveLayerIds={['vessel-clusters', 'vessel-markers']}
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
      <GnssHeatmap visible={props.showGnssZones ?? false} />
      <DuplicateMmsiLayer visible={props.showGnssZones ?? false} />
      <NetworkLayer visible={props.showNetwork ?? false} />
    </Map>
  );
}

export { MapView };
export default MapView;
