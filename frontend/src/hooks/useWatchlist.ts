import { create } from 'zustand';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useVesselStore } from './useVesselStore';

// ── Types ──────────────────────────────────────────────────────────────────

export interface WatchlistItem {
  mmsi: number;
  reason?: string;
  added_at: string;
  ship_name?: string;
  flag_country?: string;
  risk_tier?: string;
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  total: number;
}

export interface AlertEvent {
  type: 'risk_change' | 'anomaly';
  mmsi: number;
  // risk_change fields
  old_tier?: string;
  new_tier?: string;
  score?: number;
  trigger_rule?: string;
  // anomaly fields
  rule_id?: string;
  severity?: string;
  points?: number;
  details?: string;
  timestamp: string;
}

// ── Watchlist Store ────────────────────────────────────────────────────────

export interface WatchlistStore {
  watchedMmsis: Set<number>;
  setWatchlist: (mmsis: number[]) => void;
  addToWatchlist: (mmsi: number) => void;
  removeFromWatchlist: (mmsi: number) => void;
  isWatched: (mmsi: number) => boolean;
}

export const useWatchlistStore = create<WatchlistStore>((set, get) => ({
  watchedMmsis: new Set(),
  setWatchlist: (mmsis) => set({ watchedMmsis: new Set(mmsis) }),
  addToWatchlist: (mmsi) =>
    set((state) => {
      const next = new Set(state.watchedMmsis);
      next.add(mmsi);
      return { watchedMmsis: next };
    }),
  removeFromWatchlist: (mmsi) =>
    set((state) => {
      const next = new Set(state.watchedMmsis);
      next.delete(mmsi);
      return { watchedMmsis: next };
    }),
  isWatched: (mmsi) => get().watchedMmsis.has(mmsi),
}));

// ── API helpers ────────────────────────────────────────────────────────────

async function fetchWatchlist(): Promise<WatchlistResponse> {
  const res = await fetch('/api/watchlist');
  if (!res.ok) throw new Error(`Failed to fetch watchlist: ${res.status}`);
  return res.json() as Promise<WatchlistResponse>;
}

async function addToWatchlistApi(mmsi: number, reason?: string): Promise<void> {
  const res = await fetch(`/api/watchlist/${mmsi}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(`Failed to add ${mmsi} to watchlist: ${res.status}`);
}

async function removeFromWatchlistApi(mmsi: number): Promise<void> {
  const res = await fetch(`/api/watchlist/${mmsi}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to remove ${mmsi} from watchlist: ${res.status}`);
}

// ── Query hook ─────────────────────────────────────────────────────────────

export function useWatchlistQuery() {
  const setWatchlist = useWatchlistStore((s) => s.setWatchlist);

  return useQuery<WatchlistResponse>({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
    select: (data) => {
      setWatchlist(data.items.map((item) => item.mmsi));
      return data;
    },
  });
}

// ── Mutation hooks ─────────────────────────────────────────────────────────

export function useWatchlistMutations() {
  const queryClient = useQueryClient();
  const addToStore = useWatchlistStore((s) => s.addToWatchlist);
  const removeFromStore = useWatchlistStore((s) => s.removeFromWatchlist);

  const addMutation = useMutation({
    mutationFn: ({ mmsi, reason }: { mmsi: number; reason?: string }) =>
      addToWatchlistApi(mmsi, reason),
    onMutate: ({ mmsi }) => {
      // Optimistic update
      addToStore(mmsi);
    },
    onError: (_err, { mmsi }) => {
      removeFromStore(mmsi);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: ({ mmsi }: { mmsi: number }) => removeFromWatchlistApi(mmsi),
    onMutate: ({ mmsi }) => {
      // Optimistic update
      removeFromStore(mmsi);
    },
    onError: (_err, { mmsi }) => {
      addToStore(mmsi);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });

  return { addMutation, removeMutation };
}

// ── Notification helpers (exported for testing) ────────────────────────────

export function formatRiskChangeNotification(
  vesselName: string,
  event: AlertEvent,
): { title: string; body: string } {
  return {
    title: `Risk Change: ${vesselName}`,
    body: `${event.old_tier} → ${event.new_tier} (${event.trigger_rule})`,
  };
}

export function formatAnomalyNotification(
  vesselName: string,
  event: AlertEvent,
): { title: string; body: string } {
  return {
    title: `New Anomaly: ${vesselName}`,
    body: `${event.rule_id} (${event.severity})`,
  };
}

export function getVesselName(mmsi: number): string {
  const vessels = useVesselStore.getState().vessels;
  const vessel = vessels.get(mmsi);
  return vessel?.name ?? `MMSI ${mmsi}`;
}

// ── Alert WebSocket hook ───────────────────────────────────────────────────

export function useWatchlistAlerts() {
  const wsRef = useRef<WebSocket | null>(null);
  const selectVessel = useVesselStore((s) => s.selectVessel);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/alerts`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      let data: AlertEvent;
      try {
        data = JSON.parse(event.data) as AlertEvent;
      } catch {
        return;
      }

      const isWatched = useWatchlistStore.getState().isWatched(data.mmsi);
      if (!isWatched) return;

      const vesselName = getVesselName(data.mmsi);

      let notification: { title: string; body: string } | null = null;
      if (data.type === 'risk_change') {
        notification = formatRiskChangeNotification(vesselName, data);
      } else if (data.type === 'anomaly') {
        notification = formatAnomalyNotification(vesselName, data);
      }

      if (!notification) return;

      if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
        Notification.requestPermission();
      }

      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        const n = new Notification(notification.title, { body: notification.body });
        n.onclick = () => {
          window.focus();
          selectVessel(data.mmsi);
        };
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [selectVessel]);
}
