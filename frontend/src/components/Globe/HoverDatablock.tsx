import { useEffect, useRef, useState, useCallback } from 'react';
import {
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  defined,
} from 'cesium';
import { getCesiumViewer } from './cesiumViewer';
import { useVesselStore } from '../../hooks/useVesselStore';
import { RISK_COLORS } from '../../utils/riskColors';
import type { VesselState } from '../../types/vessel';

function getShipTypeLabel(shipType?: number): string {
  if (shipType == null) return 'Vessel';
  if (shipType >= 70 && shipType <= 79) return 'Cargo';
  if (shipType >= 80 && shipType <= 89) return 'Tanker';
  if (shipType >= 60 && shipType <= 69) return 'Passenger';
  if (shipType >= 30 && shipType <= 39) return 'Fishing';
  if (shipType >= 40 && shipType <= 49) return 'HSC';
  if (shipType >= 50 && shipType <= 59) return 'Special Craft';
  return 'Vessel';
}

interface HoverState {
  vessel: VesselState;
  x: number;
  y: number;
}

export function HoverDatablock() {
  const [hover, setHover] = useState<HoverState | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const lastPickTimeRef = useRef(0);
  const vessels = useVesselStore((s) => s.vessels);

  const handleMouseMove = useCallback(
    (movement: { endPosition: { x: number; y: number } }) => {
      const now = performance.now();
      // Throttle to ~60fps
      if (now - lastPickTimeRef.current < 16) return;
      lastPickTimeRef.current = now;

      const viewer = getCesiumViewer();
      if (!viewer || viewer.isDestroyed()) return;

      const picked = viewer.scene.pick(movement.endPosition);

      if (defined(picked) && picked.id && typeof picked.id.id === 'string') {
        const entityId: string = picked.id.id;
        if (entityId.startsWith('vessel-')) {
          const mmsi = parseInt(entityId.replace('vessel-', ''), 10);
          const vessel = vessels.get(mmsi);
          if (vessel) {
            setHover({
              vessel,
              x: movement.endPosition.x,
              y: movement.endPosition.y,
            });
            return;
          }
        }
      }

      setHover(null);
    },
    [vessels],
  );

  useEffect(() => {
    const viewer = getCesiumViewer();
    if (!viewer || viewer.isDestroyed()) return;

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(
      handleMouseMove,
      ScreenSpaceEventType.MOUSE_MOVE,
    );
    handlerRef.current = handler;

    return () => {
      if (!handler.isDestroyed()) {
        handler.destroy();
      }
      handlerRef.current = null;
    };
  }, [handleMouseMove]);

  if (!hover) return null;

  const { vessel, x, y } = hover;
  const riskColor = RISK_COLORS[vessel.riskTier];
  const name = vessel.name || `MMSI ${vessel.mmsi}`;
  const flag = vessel.flagCountry || '—';
  const typeLabel = getShipTypeLabel(vessel.shipType);
  const sog = vessel.sog != null ? `${vessel.sog.toFixed(1)}kn` : '—';
  const cog = vessel.cog != null ? `${Math.round(vessel.cog)}°` : '—';

  // Offset so the datablock doesn't cover the marker
  const offsetX = 14;
  const offsetY = -10;

  return (
    <div
      className="pointer-events-none fixed z-50"
      style={{
        left: x + offsetX,
        top: y + offsetY,
        maxWidth: 280,
      }}
    >
      <div
        className="flex overflow-hidden rounded"
        style={{ backgroundColor: 'rgba(30, 41, 59, 0.92)' }}
      >
        {/* Left risk colour bar */}
        <div className="w-1 shrink-0" style={{ backgroundColor: riskColor }} />

        <div className="px-2.5 py-1.5 min-w-0">
          {/* Row 1: Name + risk score */}
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
              {vessel.riskScore}
            </span>
          </div>

          {/* Row 2: IMO / flag / type */}
          <div
            className="mt-0.5 truncate text-slate-400"
            style={{ fontSize: 11 }}
          >
            MMSI {vessel.mmsi} · {flag} · {typeLabel}
          </div>

          {/* Row 3: Dynamics */}
          <div
            className="mt-0.5 text-slate-300"
            style={{ fontSize: 11 }}
          >
            {sog} · {cog}
          </div>
        </div>
      </div>
    </div>
  );
}
