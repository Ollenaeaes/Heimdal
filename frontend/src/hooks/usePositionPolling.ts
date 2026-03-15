import { useEffect, useRef, useState } from 'react';
import { useVesselStore } from './useVesselStore';

/** How often (ms) to poll for new positions */
const POLL_INTERVAL_MS = 30_000;

/**
 * Polls GET /api/vessels/positions?since=<timestamp> for new vessel positions.
 * Replaces the WebSocket-based useWebSocket hook for batch-mode operation.
 */
export function usePositionPolling(): 'polling' | 'idle' | 'error' {
  const [status, setStatus] = useState<'polling' | 'idle' | 'error'>('idle');
  const lastPollRef = useRef<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    async function poll() {
      if (!mountedRef.current) return;

      try {
        setStatus('polling');
        const since = lastPollRef.current ?? new Date(Date.now() - 5 * 60_000).toISOString();
        const res = await fetch(`/api/vessels/positions?since=${encodeURIComponent(since)}`);
        if (!res.ok) {
          setStatus('error');
          return;
        }

        const data: {
          positions: Array<{
            mmsi: number;
            lat: number;
            lon: number;
            sog: number | null;
            cog: number | null;
            heading: number | null;
            nav_status: number | null;
            timestamp: string | null;
            risk_tier: string;
            risk_score: number;
            ship_name: string | null;
            ship_type: number | null;
          }>;
          server_time: string;
        } = await res.json();

        if (!mountedRef.current) return;

        // Update store with new positions
        if (data.positions.length > 0) {
          const batch = data.positions.map((p) => ({
            mmsi: p.mmsi,
            lat: p.lat,
            lon: p.lon,
            sog: p.sog,
            cog: p.cog,
            heading: p.heading,
            navStatus: p.nav_status,
            timestamp: p.timestamp ?? new Date().toISOString(),
            riskTier: p.risk_tier as 'green' | 'yellow' | 'red',
            riskScore: p.risk_score,
            name: p.ship_name ?? undefined,
            shipType: p.ship_type ?? undefined,
          }));
          const { updatePositions } = useVesselStore.getState();
          updatePositions(batch);
        }

        lastPollRef.current = data.server_time;
        setStatus('idle');
      } catch {
        if (mountedRef.current) setStatus('error');
      }
    }

    // Initial poll
    poll();

    // Set up interval
    const timer = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, []);

  return status;
}
