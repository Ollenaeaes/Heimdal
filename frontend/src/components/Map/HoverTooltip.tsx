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

export type TooltipData = VesselTooltipData | InfraTooltipData;

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
      // Check vessel layer first
      const vesselFeatures = map.queryRenderedFeatures(e.point, {
        layers: ['vessel-markers'],
      });
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

      // Check infrastructure layers
      const infraFeatures = map.queryRenderedFeatures(e.point, {
        layers: ['infra-routes', 'infra-routes-flagged'],
      });
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
