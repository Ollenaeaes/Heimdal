import { useEffect, useState } from 'react';
import { useMap } from 'react-map-gl/maplibre';
import { useVesselStore } from '../../hooks/useVesselStore';
import { RISK_COLORS } from '../../utils/riskColors';
import type { RiskTier } from '../../utils/riskColors';

export function getShipTypeLabel(shipType?: number | null): string {
  if (shipType == null) return 'Vessel';
  if (shipType >= 70 && shipType <= 79) return 'Cargo';
  if (shipType >= 80 && shipType <= 89) return 'Tanker';
  if (shipType >= 60 && shipType <= 69) return 'Passenger';
  if (shipType >= 30 && shipType <= 39) return 'Fishing';
  if (shipType >= 40 && shipType <= 49) return 'HSC';
  if (shipType >= 50 && shipType <= 59) return 'Special Craft';
  return 'Vessel';
}

interface VesselTooltipData {
  type: 'vessel';
  x: number;
  y: number;
  mmsi: number;
}

interface InfraTooltipData {
  type: 'infrastructure';
  x: number;
  y: number;
  name: string;
  routeType: string;
}

interface AircraftTooltipData {
  type: 'aircraft';
  x: number;
  y: number;
  icaoHex: string;
  callsign: string | null;
  registration: string | null;
  description: string | null;
  category: string | null;
  country: string | null;
  altBaro: number | null;
  groundSpeed: number | null;
}

export type TooltipData = VesselTooltipData | InfraTooltipData | AircraftTooltipData;

/**
 * HoverTooltip — shows vessel/infrastructure info on hover.
 * Must be rendered as a child of a react-map-gl <Map>.
 * Manages cursor style and renders a positioned tooltip div.
 */
export function HoverTooltip() {
  const { current: map } = useMap();
  const vessels = useVesselStore((s) => s.vessels);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  // Mouse-move handler: query rendered features and update tooltip state
  useEffect(() => {
    if (!map) return;

    const onMouseMove = (e: maplibregl.MapMouseEvent) => {
      // Check vessel layers (query whichever are currently rendered)
      const vesselLayerIds = ['vessel-dots-stationary', 'vessel-arrows', 'vessel-hulls'].filter(
        (id) => !!map.getLayer(id),
      );
      const vesselFeatures = vesselLayerIds.length > 0
        ? map.queryRenderedFeatures(e.point, { layers: vesselLayerIds })
        : [];
      if (vesselFeatures.length > 0) {
        const props = vesselFeatures[0].properties;
        if (props?.mmsi != null) {
          map.getCanvas().style.cursor = 'pointer';
          setTooltip({
            type: 'vessel',
            x: e.point.x,
            y: e.point.y,
            mmsi: Number(props.mmsi),
          });
          return;
        }
      }

      // Check aircraft layer
      const acLayers = ['adsb-aircraft-icons'].filter(
        (id) => !!map.getLayer(id),
      );
      const acFeatures = acLayers.length > 0
        ? map.queryRenderedFeatures(e.point, { layers: acLayers })
        : [];
      if (acFeatures.length > 0) {
        const props = acFeatures[0].properties;
        if (props?.icao_hex) {
          map.getCanvas().style.cursor = 'pointer';
          setTooltip({
            type: 'aircraft',
            x: e.point.x,
            y: e.point.y,
            icaoHex: props.icao_hex,
            callsign: props.callsign || null,
            registration: props.registration || null,
            description: props.description || null,
            category: props.category || null,
            country: props.country || null,
            altBaro: props.alt_baro != null ? Number(props.alt_baro) : null,
            groundSpeed: props.ground_speed != null ? Number(props.ground_speed) : null,
          });
          return;
        }
      }

      // Check infrastructure layers (only if they exist)
      const infraLayers = ['infra-routes', 'infra-routes-flagged'].filter(
        (id) => !!map.getLayer(id),
      );
      const infraFeatures = infraLayers.length > 0
        ? map.queryRenderedFeatures(e.point, { layers: infraLayers })
        : [];
      if (infraFeatures.length > 0) {
        const f = infraFeatures[0];
        map.getCanvas().style.cursor = 'pointer';
        setTooltip({
          type: 'infrastructure',
          x: e.point.x,
          y: e.point.y,
          name: (f.properties?.name as string) || 'Infrastructure',
          routeType: (f.properties?.route_type as string) || '',
        });
        return;
      }

      // No feature hit — clear
      map.getCanvas().style.cursor = '';
      setTooltip(null);
    };

    const onMouseLeave = () => {
      map.getCanvas().style.cursor = '';
      setTooltip(null);
    };

    map.on('mousemove', onMouseMove);
    map.on('mouseleave', onMouseLeave);
    return () => {
      map.off('mousemove', onMouseMove);
      map.off('mouseleave', onMouseLeave);
    };
  }, [map]);

  if (!tooltip) return null;

  if (tooltip.type === 'infrastructure') {
    const routeLabel = tooltip.routeType?.replace(/_/g, ' ') || 'Infrastructure';
    return (
      <div
        className="pointer-events-none absolute z-50"
        style={{
          left: tooltip.x + 12,
          top: tooltip.y - 12,
          maxWidth: 280,
        }}
      >
        <div
          className="flex overflow-hidden rounded"
          style={{ backgroundColor: 'rgba(30, 41, 59, 0.92)' }}
        >
          <div className="w-1 shrink-0 bg-blue-500" />
          <div className="min-w-0 px-2.5 py-1.5">
            <div
              className="truncate font-semibold tracking-wide text-white"
              style={{ fontSize: 11 }}
            >
              {tooltip.name.toUpperCase()}
            </div>
            <div className="mt-0.5 text-slate-400" style={{ fontSize: 11 }}>
              {routeLabel}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (tooltip.type === 'aircraft') {
    const CATEGORY_COLORS: Record<string, string> = {
      military: '#f59e0b',
      coast_guard: '#06b6d4',
      police: '#3b82f6',
      government: '#8b5cf6',
    };
    const accentColor = CATEGORY_COLORS[tooltip.category ?? ''] ?? '#9ca3af';
    const title = tooltip.callsign || tooltip.registration || tooltip.icaoHex.toUpperCase();
    const subtitle = [
      tooltip.description,
      tooltip.country,
      tooltip.category?.replace(/_/g, ' '),
    ].filter(Boolean).join(' · ');
    const speed = tooltip.groundSpeed != null ? `${tooltip.groundSpeed.toFixed(0)}kn` : null;
    const alt = tooltip.altBaro != null ? `FL${Math.round(tooltip.altBaro / 100)}` : null;

    return (
      <div
        className="pointer-events-none absolute z-50"
        style={{ left: tooltip.x + 12, top: tooltip.y - 12, maxWidth: 300 }}
      >
        <div
          className="flex overflow-hidden rounded"
          style={{ backgroundColor: 'rgba(30, 41, 59, 0.92)' }}
        >
          <div className="w-1 shrink-0" style={{ backgroundColor: accentColor }} />
          <div className="min-w-0 px-2.5 py-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate font-semibold tracking-wide text-white" style={{ fontSize: 11 }}>
                {title.toUpperCase()}
              </span>
              <span className="shrink-0 font-mono text-slate-400" style={{ fontSize: 10 }}>
                {tooltip.icaoHex.toUpperCase()}
              </span>
            </div>
            {subtitle && (
              <div className="mt-0.5 truncate text-slate-400" style={{ fontSize: 11 }}>
                {subtitle}
              </div>
            )}
            {(speed || alt) && (
              <div className="mt-0.5 text-slate-300" style={{ fontSize: 11 }}>
                {[alt, speed].filter(Boolean).join(' · ')}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Vessel tooltip — look up full vessel data from store
  const vessel = vessels.get(tooltip.mmsi);
  const name = vessel?.name || `MMSI ${tooltip.mmsi}`;
  const riskTier = (vessel?.riskTier ?? 'green') as RiskTier;
  const riskColor = RISK_COLORS[riskTier];
  const flag = vessel?.flagCountry || null;
  const typeLabel = getShipTypeLabel(vessel?.shipType);
  const sog = vessel?.sog != null ? `${vessel.sog.toFixed(1)}kn` : null;
  const cog = vessel?.cog != null ? `${Math.round(vessel.cog)}°` : null;

  return (
    <div
      className="pointer-events-none absolute z-50"
      style={{
        left: tooltip.x + 12,
        top: tooltip.y - 12,
        maxWidth: 280,
      }}
    >
      <div
        className="flex overflow-hidden rounded"
        style={{ backgroundColor: 'rgba(30, 41, 59, 0.92)' }}
      >
        <div className="w-1 shrink-0" style={{ backgroundColor: riskColor }} />
        <div className="min-w-0 px-2.5 py-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <span
              className="truncate font-semibold tracking-wide text-white"
              style={{ fontSize: 11 }}
            >
              {name.toUpperCase()}
            </span>
            <span
              className="shrink-0 font-mono tabular-nums"
              style={{ fontSize: 11, color: riskColor }}
            >
              {vessel?.riskScore}
            </span>
          </div>
          <div className="mt-0.5 truncate text-slate-400" style={{ fontSize: 11 }}>
            MMSI {tooltip.mmsi} {flag ? `· ${flag}` : ''} · {typeLabel}
          </div>
          {(sog || cog) && (
            <div className="mt-0.5 text-slate-300" style={{ fontSize: 11 }}>
              {[sog, cog].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
