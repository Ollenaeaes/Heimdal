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

/**
 * Fetches recent anomalies from the REST API and subscribes to the /ws/alerts
 * WebSocket for real-time updates. Maintains a list of up to MAX_EVENTS events
 * sorted most-recent-first.
 */
export function useAlertStream() {
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const addEvent = useCallback((event: AlertEvent) => {
    setEvents((prev) => {
      // Deduplicate by id if present
      if (event.id != null) {
        const exists = prev.some((e) => e.id === event.id);
        if (exists) return prev;
      }
      const next = [event, ...prev];
      if (next.length > MAX_EVENTS) next.length = MAX_EVENTS;
      return next;
    });
  }, []);

  // Fetch initial anomalies from REST API
  useEffect(() => {
    let cancelled = false;

    fetch('/api/anomalies?per_page=50&resolved=false')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: { items: Array<Record<string, unknown>> }) => {
        if (cancelled) return;
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
      })
      .catch(() => {
        // REST fetch failed — WebSocket will populate events
      });

    return () => { cancelled = true; };
  }, []);

  // WebSocket connection to /ws/alerts
  useEffect(() => {
    mountedRef.current = true;
    let reconnectDelay = 1000;

    function connect() {
      if (!mountedRef.current) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/ws/alerts`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        setIsConnected(true);
        reconnectDelay = 1000;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const raw = JSON.parse(event.data as string);
          if (raw.type === 'anomaly' || raw.type === 'risk_change') {
            const alert: AlertEvent = {
              id: raw.id ?? raw.anomaly_id,
              mmsi: raw.mmsi,
              vesselName: raw.vessel_name ?? raw.vesselName,
              ruleId: raw.rule_id ?? raw.ruleId ?? 'unknown',
              severity: raw.severity ?? 'low',
              points: raw.points,
              details: raw.details,
              timestamp: raw.created_at ?? raw.timestamp ?? new Date().toISOString(),
              lat: raw.lat ?? raw.details?.lat,
              lon: raw.lon ?? raw.details?.lon,
            };
            addEvent(alert);
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (!mountedRef.current) return;
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          reconnectDelay = Math.min(reconnectDelay * 2, 60000);
          connect();
        }, reconnectDelay);
      };

      ws.onerror = () => {
        // onclose fires after onerror
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [addEvent]);

  return { events, isConnected };
}
