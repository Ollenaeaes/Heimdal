import { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { TrackPoint, GfwEvent } from '../types/api';
import { useReplayStore } from './useReplayStore';

export interface AisGapSegment {
  startIndex: number;
  endIndex: number;
  startTime: string;
  endTime: string;
  gapHours: number;
}

/** Gap threshold in hours for detecting AIS gaps */
const AIS_GAP_THRESHOLD_HOURS = 6;

export interface TrackReplayState {
  isActive: boolean;
  isPlaying: boolean;
  currentIndex: number;
  playbackSpeed: number;
  track: TrackPoint[] | undefined;
  trackLoading: boolean;
  gfwEvents: GfwEvent[] | undefined;
  gfwLoading: boolean;
  aisGaps: AisGapSegment[];
  currentPoint: TrackPoint | null;
  progress: number; // 0-100
  activate: () => void;
  deactivate: () => void;
  play: () => void;
  pause: () => void;
  togglePlayPause: () => void;
  setSpeed: (speed: number) => void;
  seekToIndex: (index: number) => void;
  seekToProgress: (percent: number) => void;
}

async function fetchFullTrack(mmsi: number): Promise<TrackPoint[]> {
  const res = await fetch(`/api/vessels/${mmsi}/track`);
  if (!res.ok) throw new Error(`Failed to fetch track for ${mmsi}: ${res.status}`);
  return res.json() as Promise<TrackPoint[]>;
}

async function fetchGfwEvents(mmsi: number): Promise<GfwEvent[]> {
  const res = await fetch(`/api/gfw/events?mmsi=${mmsi}`);
  if (!res.ok) throw new Error(`Failed to fetch GFW events for ${mmsi}: ${res.status}`);
  return res.json() as Promise<GfwEvent[]>;
}

export function detectAisGaps(track: TrackPoint[]): AisGapSegment[] {
  const gaps: AisGapSegment[] = [];
  for (let i = 1; i < track.length; i++) {
    const prevTime = new Date(track[i - 1].timestamp).getTime();
    const currTime = new Date(track[i].timestamp).getTime();
    const diffHours = (currTime - prevTime) / (1000 * 60 * 60);
    if (diffHours >= AIS_GAP_THRESHOLD_HOURS) {
      gaps.push({
        startIndex: i - 1,
        endIndex: i,
        startTime: track[i - 1].timestamp,
        endTime: track[i].timestamp,
        gapHours: Math.round(diffHours * 10) / 10,
      });
    }
  }
  return gaps;
}

export function useTrackReplay(mmsi: number | null): TrackReplayState {
  const [isActive, setIsActive] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const animFrameRef = useRef<number | null>(null);
  const lastTickRef = useRef<number>(0);

  const { data: track, isLoading: trackLoading } = useQuery<TrackPoint[]>({
    queryKey: ['vessel-track-full', mmsi],
    queryFn: () => fetchFullTrack(mmsi!),
    enabled: isActive && mmsi !== null,
  });

  const { data: gfwEvents, isLoading: gfwLoading } = useQuery<GfwEvent[]>({
    queryKey: ['gfw-events-vessel', mmsi],
    queryFn: () => fetchGfwEvents(mmsi!),
    enabled: isActive && mmsi !== null,
  });

  const aisGaps = track ? detectAisGaps(track) : [];

  // Sync replay state to the globe store
  const setReplayState = useReplayStore((s) => s.setReplayState);
  const clearReplay = useReplayStore((s) => s.clearReplay);

  useEffect(() => {
    if (isActive && track) {
      setReplayState({ isActive, track, currentIndex, aisGaps });
    } else if (!isActive) {
      clearReplay();
    }
  }, [isActive, track, currentIndex, aisGaps, setReplayState, clearReplay]);

  const trackLength = track?.length ?? 0;
  const currentPoint = track && track.length > 0 ? track[currentIndex] ?? null : null;
  const progress = trackLength > 1 ? (currentIndex / (trackLength - 1)) * 100 : 0;

  // Animation loop
  useEffect(() => {
    if (!isPlaying || !track || track.length === 0) return;

    // Base interval: 100ms per point at speed 1x
    const baseIntervalMs = 100;
    const intervalMs = baseIntervalMs / playbackSpeed;

    const tick = (timestamp: number) => {
      if (timestamp - lastTickRef.current >= intervalMs) {
        lastTickRef.current = timestamp;
        setCurrentIndex((prev) => {
          if (prev >= track.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }
      animFrameRef.current = requestAnimationFrame(tick);
    };

    lastTickRef.current = performance.now();
    animFrameRef.current = requestAnimationFrame(tick);

    return () => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [isPlaying, playbackSpeed, track]);

  const activate = useCallback(() => {
    setIsActive(true);
    setCurrentIndex(0);
    setIsPlaying(false);
  }, []);

  const deactivate = useCallback(() => {
    setIsActive(false);
    setIsPlaying(false);
    setCurrentIndex(0);
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
  }, []);

  const play = useCallback(() => setIsPlaying(true), []);
  const pause = useCallback(() => setIsPlaying(false), []);
  const togglePlayPause = useCallback(() => setIsPlaying((p) => !p), []);

  const setSpeed = useCallback((speed: number) => {
    setPlaybackSpeed(speed);
  }, []);

  const seekToIndex = useCallback(
    (index: number) => {
      if (!track) return;
      const clamped = Math.max(0, Math.min(index, track.length - 1));
      setCurrentIndex(clamped);
    },
    [track]
  );

  const seekToProgress = useCallback(
    (percent: number) => {
      if (!track || track.length === 0) return;
      const index = Math.round((percent / 100) * (track.length - 1));
      setCurrentIndex(Math.max(0, Math.min(index, track.length - 1)));
    },
    [track]
  );

  return {
    isActive,
    isPlaying,
    currentIndex,
    playbackSpeed,
    track,
    trackLoading,
    gfwEvents,
    gfwLoading,
    aisGaps,
    currentPoint,
    progress,
    activate,
    deactivate,
    play,
    pause,
    togglePlayPause,
    setSpeed,
    seekToIndex,
    seekToProgress,
  };
}
