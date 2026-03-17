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
  darkShipsOnly: boolean;
  showGfwEventTypes: string[];
}

export interface VesselStore {
  vessels: Map<number, VesselState>;
  positionHistory: Map<number, PositionHistoryEntry[]>;
  selectedMmsi: number | null;
  spoofedMmsis: Set<number>;
  filters: FilterState;
  updatePosition: (update: VesselState) => void;
  updatePositions: (updates: VesselState[]) => void;
  replaceGreenVessels: (greenVessels: VesselState[]) => void;
  clearOldPositions: (maxAgeMs: number) => void;
  selectVessel: (mmsi: number | null) => void;
  setFilter: (filter: Partial<FilterState>) => void;
  addSpoofedMmsi: (mmsi: number) => void;
  removeSpoofedMmsi: (mmsi: number) => void;
  setSpoofedMmsis: (mmsis: Set<number>) => void;
}

export const useVesselStore = create<VesselStore>((set) => ({
  vessels: new Map(),
  positionHistory: new Map(),
  selectedMmsi: null,
  spoofedMmsis: new Set<number>(),
  filters: {
    riskTiers: new Set(),
    shipTypes: [],
    bbox: null,
    activeSince: null,
    darkShipsOnly: false,
    showGfwEventTypes: ['ENCOUNTER', 'LOITERING', 'AIS_DISABLING', 'PORT_VISIT'],
  },
  updatePosition: (update) =>
    set((state) => {
      const newVessels = new Map(state.vessels);
      newVessels.set(update.mmsi, update);
      return { vessels: newVessels };
    }),
  updatePositions: (updates) =>
    set((state) => {
      const newVessels = new Map(state.vessels);
      for (const update of updates) {
        newVessels.set(update.mmsi, update);
      }
      return { vessels: newVessels };
    }),
  replaceGreenVessels: (greenVessels) =>
    set((state) => {
      // Remove all existing green vessels, then add the new set
      const newVessels = new Map<number, VesselState>();
      for (const [mmsi, v] of state.vessels) {
        if (v.riskTier !== 'green') {
          newVessels.set(mmsi, v);
        }
      }
      for (const v of greenVessels) {
        newVessels.set(v.mmsi, v);
      }
      return { vessels: newVessels };
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
  addSpoofedMmsi: (mmsi) =>
    set((state) => {
      const next = new Set(state.spoofedMmsis);
      next.add(mmsi);
      return { spoofedMmsis: next };
    }),
  removeSpoofedMmsi: (mmsi) =>
    set((state) => {
      const next = new Set(state.spoofedMmsis);
      next.delete(mmsi);
      return { spoofedMmsis: next };
    }),
  setSpoofedMmsis: (mmsis) => set({ spoofedMmsis: mmsis }),
}));
