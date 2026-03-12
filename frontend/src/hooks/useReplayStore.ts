import { create } from 'zustand';
import type { TrackPoint } from '../types/api';
import type { AisGapSegment } from './useTrackReplay';

export interface ReplayGlobeState {
  isActive: boolean;
  track: TrackPoint[] | null;
  currentIndex: number;
  aisGaps: AisGapSegment[];
  setReplayState: (state: {
    isActive: boolean;
    track: TrackPoint[] | null;
    currentIndex: number;
    aisGaps: AisGapSegment[];
  }) => void;
  clearReplay: () => void;
}

export const useReplayStore = create<ReplayGlobeState>((set) => ({
  isActive: false,
  track: null,
  currentIndex: 0,
  aisGaps: [],
  setReplayState: (state) => set(state),
  clearReplay: () =>
    set({ isActive: false, track: null, currentIndex: 0, aisGaps: [] }),
}));
