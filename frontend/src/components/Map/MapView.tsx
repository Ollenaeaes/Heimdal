import { useCallback } from 'react';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapRef } from 'react-map-gl/maplibre';
import { setMapInstance, INITIAL_CENTER, INITIAL_ZOOM } from './mapInstance';
import { createMapStyle } from './style';

export interface MapViewProps {
  showGfwEvents?: boolean;
  showSarDetections?: boolean;
  showInfrastructure?: boolean;
  showGnssZones?: boolean;
  showNetwork?: boolean;
}

const mapStyle = createMapStyle();

function MapView(_props: MapViewProps) {
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
    />
  );
}

export { MapView };
export default MapView;
