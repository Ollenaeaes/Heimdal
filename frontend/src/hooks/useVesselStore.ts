import { create } from 'zustand';
import type { VesselState } from '../types/vessel';

export interface FilterState {
  riskTiers: Set<string>;
  shipTypes: number[];
  bbox: [number, number, number, number] | null;
  activeSince: string | null;
}

export interface VesselStore {
  vessels: Map<number, VesselState>;
  selectedMmsi: number | null;
  filters: FilterState;
  updatePosition: (update: VesselState) => void;
  selectVessel: (mmsi: number | null) => void;
  setFilter: (filter: Partial<FilterState>) => void;
}

export const useVesselStore = create<VesselStore>((set) => ({
  vessels: new Map(),
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
      return { vessels: newVessels };
    }),
  selectVessel: (mmsi) => set({ selectedMmsi: mmsi }),
  setFilter: (filter) =>
    set((state) => ({ filters: { ...state.filters, ...filter } })),
}));
