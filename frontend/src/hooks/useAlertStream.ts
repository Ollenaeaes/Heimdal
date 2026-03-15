import { useState, useEffect, useRef, useCallback } from 'react';

export interface AlertEvent {
  id?: number;
  mmsi: number;
  vesselName?: string;
  ruleId: string;
  severity: 'critical' | 'high' | 'moderate' | 'low';
  points?: number;
  details?: Record<string, unknown>;
  timestamp: string;
  lat?: number;
  lon?: number;
}

const MAX_EVENTS = 200;

/** How often (ms) to poll for new anomalies */
const POLL_INTERVAL_MS = 60_000;

/**
 * Polls the REST API for recent anomalies on an interval.
 * Replaces the WebSocket-based alert stream for batch-mode operation.
 */
export function useAlertStream() {
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const mountedRef = useRef(true);

  const fetchAnomalies = useCallback(async () => {
    try {
      const res = await fetch('/api/anomalies?per_page=50&resolved=false');
      if (!res.ok) return;
      const data: { items: Array<Record<string, unknown>> } = await res.json();
      if (!mountedRef.current) return;

      const mapped: AlertEvent[] = (data.items ?? []).map((item) => ({
        id: item.id as number | undefined,
        mmsi: item.mmsi as number,
        vesselName: (item.vessel_name as string) ?? undefined,
        ruleId: item.rule_id as string,
        severity: item.severity as AlertEvent['severity'],
        points: item.points as number | undefined,
        details: item.details as Record<string, unknown> | undefined,
        timestamp: item.created_at as string,
        lat: (item.details as Record<string, unknown> | undefined)?.lat as number | undefined,
        lon: (item.details as Record<string, unknown> | undefined)?.lon as number | undefined,
      }));
      setEvents(mapped.slice(0, MAX_EVENTS));
    } catch {
      // Fetch failed — will retry on next interval
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    // Initial fetch
    fetchAnomalies();

    // Poll on interval
    const timer = setInterval(fetchAnomalies, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, [fetchAnomalies]);

  return { events, isConnected: true };
}
