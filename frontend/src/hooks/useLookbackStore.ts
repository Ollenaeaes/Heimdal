import { create } from 'zustand';
import type { TrackPoint } from '../types/api';

export interface LookbackConfig {
  vessels: number[];
  dateRange: { start: Date; end: Date };
  showNetwork: boolean;
}

export interface LookbackState {
  // Configuration (set before playback starts)
  isActive: boolean;
  selectedVessels: number[];
  networkVessels: number[];
  showNetwork: boolean;
  dateRange: { start: Date; end: Date };

  // Area lookback mode
  isAreaMode: boolean;
  areaPolygon: [number, number][] | null;
  isDrawing: boolean;

  // Playback state
  isPlaying: boolean;
  playbackSpeed: number;
  currentTime: Date;

  // GNSS overlay during playback
  showGnssOverlay: boolean;
  gnssOverlayWindow: '1h' | '3h' | '6h';
  gnssZonesCache: GeoJSON.FeatureCollection | null;

  // Track data (keyed by MMSI)
  tracks: Map<number, TrackPoint[]>;
  trackErrors: Map<number, string>;

  // Actions
  configure: (config: LookbackConfig) => void;
  configureArea: (polygon: [number, number][], vessels: number[], dateRange: { start: Date; end: Date }) => void;
  activate: () => void;
  deactivate: () => void;
  play: () => void;
  pause: () => void;
  setSpeed: (speed: number) => void;
  seekToTime: (time: Date) => void;
  seekToProgress: (percent: number) => void;
  setTracks: (mmsi: number, track: TrackPoint[]) => void;
  setTrackError: (mmsi: number, error: string) => void;
  startDrawing: () => void;
  finishDrawing: (polygon: [number, number][]) => void;
  cancelDrawing: () => void;
  toggleGnssOverlay: () => void;
  setGnssOverlayWindow: (w: '1h' | '3h' | '6h') => void;
  setGnssZonesCache: (data: GeoJSON.FeatureCollection | null) => void;
}

const defaultDateRange = () => {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 7);
  return { start, end };
};

export const useLookbackStore = create<LookbackState>((set, get) => ({
  isActive: false,
  selectedVessels: [],
  networkVessels: [],
  showNetwork: false,
  dateRange: defaultDateRange(),

  isAreaMode: false,
  areaPolygon: null,
  isDrawing: false,

  isPlaying: false,
  playbackSpeed: 60,
  currentTime: new Date(),

  showGnssOverlay: false,
  gnssOverlayWindow: '6h',
  gnssZonesCache: null,

  tracks: new Map(),
  trackErrors: new Map(),

  configure: (config) =>
    set({
      selectedVessels: config.vessels,
      dateRange: config.dateRange,
      showNetwork: config.showNetwork,
      isAreaMode: false,
      areaPolygon: null,
      tracks: new Map(),
      trackErrors: new Map(),
    }),

  configureArea: (polygon, vessels, dateRange) =>
    set({
      isAreaMode: true,
      areaPolygon: polygon,
      selectedVessels: vessels,
      dateRange,
      showNetwork: false,
      networkVessels: [],
      tracks: new Map(),
      trackErrors: new Map(),
    }),

  activate: () => {
    const { dateRange } = get();
    set({
      isActive: true,
      isPlaying: false,
      currentTime: dateRange.start,
      playbackSpeed: 60,
    });
  },

  deactivate: () =>
    set({
      isActive: false,
      isPlaying: false,
      isAreaMode: false,
      areaPolygon: null,
      isDrawing: false,
      selectedVessels: [],
      networkVessels: [],
      tracks: new Map(),
      trackErrors: new Map(),
      currentTime: new Date(),
      dateRange: defaultDateRange(),
      showGnssOverlay: false,
      gnssZonesCache: null,
    }),

  play: () => set({ isPlaying: true }),
  pause: () => set({ isPlaying: false }),

  setSpeed: (speed) => set({ playbackSpeed: speed }),

  seekToTime: (time) => set({ currentTime: time }),

  seekToProgress: (percent) => {
    const { dateRange } = get();
    const totalMs = dateRange.end.getTime() - dateRange.start.getTime();
    const offsetMs = (percent / 100) * totalMs;
    set({ currentTime: new Date(dateRange.start.getTime() + offsetMs) });
  },

  setTracks: (mmsi, track) =>
    set((state) => {
      const newTracks = new Map(state.tracks);
      newTracks.set(mmsi, track);
      return { tracks: newTracks };
    }),

  setTrackError: (mmsi, error) =>
    set((state) => {
      const newErrors = new Map(state.trackErrors);
      newErrors.set(mmsi, error);
      return { trackErrors: newErrors };
    }),

  startDrawing: () => set({ isDrawing: true }),

  finishDrawing: (polygon) =>
    set({ isDrawing: false, areaPolygon: polygon }),

  cancelDrawing: () =>
    set({ isDrawing: false, areaPolygon: null }),

  toggleGnssOverlay: () =>
    set((state) => ({ showGnssOverlay: !state.showGnssOverlay })),

  setGnssOverlayWindow: (w) => set({ gnssOverlayWindow: w }),

  setGnssZonesCache: (data) => set({ gnssZonesCache: data }),
}));
