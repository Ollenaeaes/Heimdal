import { Entity, PolygonGraphics, PointGraphics, LabelGraphics, PolylineGraphics } from 'resium';
import { Cartesian3, Color, LabelStyle, VerticalOrigin, Cartesian2, MaterialProperty, PolylineDashMaterialProperty } from 'cesium';
import stsZonesData from '../../data/stsZones.json';
import terminalsData from '../../data/terminals.json';
import eezData from '../../data/eezBoundaries.json';

export interface OverlayProps {
  showStsZones: boolean;
  showTerminals: boolean;
  showEez: boolean;
}

/** STS zone fill color: semi-transparent amber */
const STS_FILL_COLOR = Color.fromCssColorString('rgba(212, 130, 12, 0.15)');
/** STS zone outline color: amber */
const STS_OUTLINE_COLOR = Color.fromCssColorString('#D4820C');
/** Terminal marker color: red */
const TERMINAL_COLOR = Color.fromCssColorString('#C0392B');
/** EEZ line color: blue dashed */
const EEZ_COLOR = Color.BLUE;

/** Convert GeoJSON [lon, lat] polygon ring to Cesium Cartesian3 array */
function polygonToCartesian(coordinates: number[][]): Cartesian3[] {
  return coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat));
}

/** Compute centroid of a polygon ring for label placement */
function polygonCentroid(coordinates: number[][]): Cartesian3 {
  const ring = coordinates.slice(0, -1); // remove closing point
  const sumLon = ring.reduce((s, c) => s + c[0], 0) / ring.length;
  const sumLat = ring.reduce((s, c) => s + c[1], 0) / ring.length;
  return Cartesian3.fromDegrees(sumLon, sumLat);
}

/** Convert GeoJSON LineString coordinates to Cesium Cartesian3 array */
function lineToCartesian(coordinates: number[][]): Cartesian3[] {
  return coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat));
}

export function Overlays({ showStsZones, showTerminals, showEez }: OverlayProps) {
  return (
    <>
      {/* STS Zone Polygons */}
      {showStsZones &&
        stsZonesData.features.map((feature) => {
          const coords = feature.geometry.coordinates[0];
          const hierarchy = polygonToCartesian(coords);
          const labelPos = polygonCentroid(coords);
          return (
            <Entity key={feature.properties.id} position={labelPos}>
              <PolygonGraphics
                hierarchy={hierarchy}
                material={STS_FILL_COLOR as unknown as MaterialProperty}
                outline
                outlineColor={STS_OUTLINE_COLOR}
                outlineWidth={2}
              />
              <LabelGraphics
                text={feature.properties.name}
                font="12px sans-serif"
                fillColor={STS_OUTLINE_COLOR}
                style={LabelStyle.FILL_AND_OUTLINE}
                outlineColor={Color.BLACK}
                outlineWidth={2}
                verticalOrigin={VerticalOrigin.BOTTOM}
                pixelOffset={new Cartesian2(0, -10)}
              />
            </Entity>
          );
        })}

      {/* Russian Terminal Point Markers */}
      {showTerminals &&
        terminalsData.features.map((feature) => {
          const [lon, lat] = feature.geometry.coordinates;
          const position = Cartesian3.fromDegrees(lon, lat);
          return (
            <Entity key={feature.properties.id} position={position}>
              <PointGraphics
                pixelSize={16}
                color={TERMINAL_COLOR}
                outlineColor={Color.WHITE}
                outlineWidth={1}
              />
              <LabelGraphics
                text={feature.properties.name}
                font="12px sans-serif"
                fillColor={Color.WHITE}
                style={LabelStyle.FILL_AND_OUTLINE}
                outlineColor={Color.BLACK}
                outlineWidth={2}
                verticalOrigin={VerticalOrigin.BOTTOM}
                pixelOffset={new Cartesian2(0, -14)}
              />
            </Entity>
          );
        })}

      {/* Norwegian EEZ Boundary */}
      {showEez &&
        eezData.features.map((feature) => {
          const positions = lineToCartesian(feature.geometry.coordinates);
          return (
            <Entity key={feature.properties.id}>
              <PolylineGraphics
                positions={positions}
                width={2}
                material={new PolylineDashMaterialProperty({
                  color: EEZ_COLOR,
                  dashLength: 16,
                })}
              />
            </Entity>
          );
        })}
    </>
  );
}

export interface OverlayToggleState {
  showStsZones: boolean;
  showTerminals: boolean;
  showEez: boolean;
}

export interface OverlayTogglesProps {
  state: OverlayToggleState;
  onChange: (newState: OverlayToggleState) => void;
}

export function OverlayToggles({ state, onChange }: OverlayTogglesProps) {
  const toggle = (key: keyof OverlayToggleState) => {
    onChange({ ...state, [key]: !state[key] });
  };

  return (
    <div className="flex flex-col gap-2 bg-gray-900/80 p-3 rounded-lg text-white text-sm">
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showStsZones}
          onChange={() => toggle('showStsZones')}
          className="accent-amber-500"
        />
        STS Zones
      </label>
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showTerminals}
          onChange={() => toggle('showTerminals')}
          className="accent-red-500"
        />
        Russian Terminals
      </label>
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={state.showEez}
          onChange={() => toggle('showEez')}
          className="accent-blue-500"
        />
        Norwegian EEZ
      </label>
    </div>
  );
}
