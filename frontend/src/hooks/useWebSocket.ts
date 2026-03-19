import { useEffect, useRef, useCallback, useSyncExternalStore } from 'react';
import { useVesselStore } from './useVesselStore';
import type { FilterState } from './useVesselStore';
import type { VesselState } from '../types/vessel';

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

interface SubscriptionMessage {
  type: 'subscribe';
  filters: {
    risk_tiers: string[];
    ship_types: number[];
    bbox: [number, number, number, number] | null;
  };
}

function buildSubscriptionMessage(filters: FilterState): SubscriptionMessage {
  return {
    type: 'subscribe',
    filters: {
      risk_tiers: Array.from(filters.riskTiers),
      ship_types: filters.shipTypes,
      bbox: filters.bbox,
    },
  };
}

const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 60000;
const RECONNECT_MULTIPLIER = 2;

/** How often (ms) to flush buffered vessel updates into the store */
const FLUSH_INTERVAL_MS = 2000;

/**
 * Manages a WebSocket connection to the vessel positions endpoint.
 * Buffers incoming positions and flushes to the store every FLUSH_INTERVAL_MS
 * to avoid overwhelming React with per-message re-renders.
 */
export function useWebSocket(): ConnectionStatus {
  const statusRef = useRef<ConnectionStatus>('disconnected');
  const listenersRef = useRef(new Set<() => void>());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // Buffer for incoming vessel updates — flushed periodically
  const bufferRef = useRef<Map<number, VesselState>>(new Map());
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const setStatus = useCallback((next: ConnectionStatus) => {
    if (statusRef.current !== next) {
      statusRef.current = next;
      listenersRef.current.forEach((l) => l());
    }
  }, []);

  const subscribe = useCallback((listener: () => void) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const getSnapshot = useCallback(() => statusRef.current, []);

  const status = useSyncExternalStore(subscribe, getSnapshot);

  const sendSubscription = useCallback((ws: WebSocket, filters: FilterState) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(buildSubscriptionMessage(filters)));
    }
  }, []);

  // Start periodic flush
  useEffect(() => {
    flushTimerRef.current = setInterval(() => {
      const buf = bufferRef.current;
      if (buf.size === 0) return;
      const batch = Array.from(buf.values());
      buf.clear();
      const { updatePositions } = useVesselStore.getState();
      updatePositions(batch);
    }, FLUSH_INTERVAL_MS);

    return () => {
      if (flushTimerRef.current) clearInterval(flushTimerRef.current);
    };
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
    }

    setStatus('connecting');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/positions`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close();
        return;
      }
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
      setStatus('connected');
      const filters = useVesselStore.getState().filters;
      sendSubscription(ws, filters);
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const raw = JSON.parse(event.data as string);
        const items = Array.isArray(raw) ? raw : [raw];
        const store = useVesselStore.getState();
        for (const d of items) {
          if (!d.mmsi || d.lat == null || d.lon == null) continue;
          // Merge: update position fields from stream, preserve
          // risk/identity fields from the snapshot/store
          const existing = bufferRef.current.get(d.mmsi) ?? store.vessels.get(d.mmsi);
          bufferRef.current.set(d.mmsi, {
            ...existing,
            mmsi: d.mmsi,
            lat: d.lat,
            lon: d.lon,
            sog: d.sog ?? null,
            cog: d.cog ?? null,
            heading: d.heading ?? null,
            navStatus: d.nav_status ?? existing?.navStatus ?? null,
            timestamp: d.timestamp ?? existing?.timestamp ?? new Date().toISOString(),
            // Preserve fields the stream doesn't provide
            riskTier: existing?.riskTier ?? 'green',
            riskScore: existing?.riskScore ?? 0,
            name: existing?.name,
            shipType: existing?.shipType,
          });
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setStatus('disconnected');
      if (!mountedRef.current) return;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will fire after onerror, which handles reconnection
    };
  }, [setStatus, sendSubscription]);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    if (reconnectTimerRef.current !== null) return;

    const delay = reconnectDelayRef.current;
    reconnectDelayRef.current = Math.min(
      delay * RECONNECT_MULTIPLIER,
      MAX_RECONNECT_DELAY,
    );

    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, delay);
  }, [connect]);

  // Connect on mount, clean up on unmount
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  // Re-subscribe when filters change
  useEffect(() => {
    let prevFilters = useVesselStore.getState().filters;
    return useVesselStore.subscribe((state) => {
      if (state.filters !== prevFilters) {
        prevFilters = state.filters;
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          sendSubscription(ws, state.filters);
        }
      }
    });
  }, [sendSubscription]);

  return status;
}
