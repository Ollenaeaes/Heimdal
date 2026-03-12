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

/**
 * Manages a WebSocket connection to the vessel positions endpoint.
 * Automatically subscribes with current filters, handles reconnection
 * with exponential backoff, and updates the vessel store on messages.
 */
export function useWebSocket(): ConnectionStatus {
  const statusRef = useRef<ConnectionStatus>('disconnected');
  const listenersRef = useRef(new Set<() => void>());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

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
        const data: unknown = JSON.parse(event.data as string);
        const vessels: VesselState[] = Array.isArray(data) ? data : [data];
        const { updatePosition } = useVesselStore.getState();
        for (const vessel of vessels) {
          updatePosition(vessel);
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
