import { create } from 'zustand';
import type { VesselState } from '../types/vessel';

export interface PositionHistoryEntry {
  lat: number;
  lon: number;
  timestamp: string;
}

/** Maximum number of history entries per vessel (ring buffer cap) */
export const MAX_HISTORY_PER_VESSEL = 500;

export interface FilterState {
  riskTiers: Set<string>;
  shipTypes: number[];
  bbox: [number, number, number, number] | null;
  activeSince: string | null;
}

export interface VesselStore {
  vessels: Map<number, VesselState>;
  positionHistory: Map<number, PositionHistoryEntry[]>;
  selectedMmsi: number | null;
  filters: FilterState;
  updatePosition: (update: VesselState) => void;
  clearOldPositions: (maxAgeMs: number) => void;
  selectVessel: (mmsi: number | null) => void;
  setFilter: (filter: Partial<FilterState>) => void;
}

export const useVesselStore = create<VesselStore>((set) => ({
  vessels: new Map(),
  positionHistory: new Map(),
  selectedMmsi: null,
  filters: {
    riskTiers: new Set(),
    shipTypes: [],
    bbox: null,
    activeSince: null,
  },
  updatePosition: (update) =>
    set((state) => {
      const newVessels = new Map(state.vessels);
      newVessels.set(update.mmsi, update);

      const newHistory = new Map(state.positionHistory);
      const existing = newHistory.get(update.mmsi) ?? [];
      const entry: PositionHistoryEntry = {
        lat: update.lat,
        lon: update.lon,
        timestamp: update.timestamp,
      };
      // Append and cap at MAX_HISTORY_PER_VESSEL (drop oldest entries)
      const updated = [...existing, entry];
      if (updated.length > MAX_HISTORY_PER_VESSEL) {
        newHistory.set(update.mmsi, updated.slice(updated.length - MAX_HISTORY_PER_VESSEL));
      } else {
        newHistory.set(update.mmsi, updated);
      }

      return { vessels: newVessels, positionHistory: newHistory };
    }),
  clearOldPositions: (maxAgeMs) =>
    set((state) => {
      const now = Date.now();
      const newHistory = new Map<number, PositionHistoryEntry[]>();
      for (const [mmsi, entries] of state.positionHistory) {
        const filtered = entries.filter(
          (e) => now - new Date(e.timestamp).getTime() <= maxAgeMs
        );
        if (filtered.length > 0) {
          newHistory.set(mmsi, filtered);
        }
      }
      return { positionHistory: newHistory };
    }),
  selectVessel: (mmsi) => set({ selectedMmsi: mmsi }),
  setFilter: (filter) =>
    set((state) => ({ filters: { ...state.filters, ...filter } })),
}));
