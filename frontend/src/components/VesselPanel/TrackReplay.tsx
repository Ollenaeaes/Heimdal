import type { TrackReplayState } from '../../hooks/useTrackReplay';
import { formatTimestampAbsolute, formatSpeed, formatCourse } from '../../utils/formatters';

const SPEED_OPTIONS = [0.5, 1, 2, 5, 10];

interface TrackReplayProps {
  replay: TrackReplayState;
}

export function TrackReplay({ replay }: TrackReplayProps) {
  const {
    isActive,
    isPlaying,
    currentIndex,
    playbackSpeed,
    track,
    trackLoading,
    gfwEvents,
    aisGaps,
    currentPoint,
    progress,
    activate,
    deactivate,
    togglePlayPause,
    setSpeed,
    seekToProgress,
  } = replay;

  if (!isActive) {
    return (
      <div className="px-4 py-3 border-b border-gray-700" data-testid="track-replay-section">
        <button
          data-testid="replay-activate"
          onClick={activate}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white rounded text-sm transition-colors"
        >
          <span>&#9654;</span>
          Replay Track
        </button>
      </div>
    );
  }

  if (trackLoading) {
    return (
      <div className="px-4 py-3 border-b border-gray-700" data-testid="track-replay-section">
        <div className="text-xs text-gray-500">Loading track data for replay...</div>
      </div>
    );
  }

  if (!track || track.length === 0) {
    return (
      <div className="px-4 py-3 border-b border-gray-700" data-testid="track-replay-section">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">No track data available for replay</span>
          <button
            data-testid="replay-close"
            onClick={deactivate}
            className="text-gray-400 hover:text-white text-xs"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  const trackStart = track[0].timestamp;
  const trackEnd = track[track.length - 1].timestamp;
  const totalTimeMs = new Date(trackEnd).getTime() - new Date(trackStart).getTime();

  // Calculate gap segments as percentage ranges on the timeline
  const gapSegments = aisGaps.map((gap) => {
    const startMs = new Date(gap.startTime).getTime() - new Date(trackStart).getTime();
    const endMs = new Date(gap.endTime).getTime() - new Date(trackStart).getTime();
    return {
      left: totalTimeMs > 0 ? (startMs / totalTimeMs) * 100 : 0,
      width: totalTimeMs > 0 ? ((endMs - startMs) / totalTimeMs) * 100 : 0,
      gapHours: gap.gapHours,
    };
  });

  // Calculate GFW event positions on timeline
  const gfwMarkers = (gfwEvents ?? []).map((evt) => {
    const evtMs = new Date(evt.startTime).getTime() - new Date(trackStart).getTime();
    return {
      id: evt.id,
      type: evt.type,
      left: totalTimeMs > 0 ? Math.max(0, Math.min(100, (evtMs / totalTimeMs) * 100)) : 0,
    };
  });

  const gfwTypeColors: Record<string, string> = {
    ENCOUNTER: '#D4820C',
    LOITERING: '#7F1D1D',
    AIS_DISABLING: '#DC2626',
    PORT_VISIT: '#3B82F6',
  };

  const handleScrubberClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percent = (x / rect.width) * 100;
    seekToProgress(Math.max(0, Math.min(100, percent)));
  };

  return (
    <div className="px-4 py-3 border-b border-gray-700 space-y-3" data-testid="track-replay-section">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          Track Replay
        </h4>
        <button
          data-testid="replay-close"
          onClick={deactivate}
          className="text-gray-400 hover:text-white text-xs"
          aria-label="Close replay"
        >
          Close
        </button>
      </div>

      {/* Play controls */}
      <div className="flex items-center gap-3">
        <button
          data-testid="replay-play-pause"
          onClick={togglePlayPause}
          className="w-8 h-8 flex items-center justify-center bg-gray-800 hover:bg-gray-700 rounded text-gray-300 hover:text-white transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? '\u23F8' : '\u25B6'}
        </button>

        {/* Speed selector */}
        <div className="flex items-center gap-1" data-testid="replay-speed-controls">
          {SPEED_OPTIONS.map((speed) => (
            <button
              key={speed}
              data-testid={`replay-speed-${speed}x`}
              onClick={() => setSpeed(speed)}
              className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                playbackSpeed === speed
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              {speed}x
            </button>
          ))}
        </div>

        {/* Point counter */}
        <span className="text-xs text-gray-500 ml-auto">
          {currentIndex + 1} / {track.length}
        </span>
      </div>

      {/* Timeline scrubber */}
      <div
        data-testid="replay-timeline"
        className="relative h-6 bg-gray-800 rounded cursor-pointer"
        onClick={handleScrubberClick}
      >
        {/* AIS gap segments (red) */}
        {gapSegments.map((gap, i) => (
          <div
            key={`gap-${i}`}
            data-testid={`replay-gap-${i}`}
            className="absolute top-0 bottom-0 bg-red-900/60 z-10"
            style={{ left: `${gap.left}%`, width: `${gap.width}%` }}
            title={`AIS Gap: ${gap.gapHours}h`}
          />
        ))}

        {/* GFW event markers */}
        {gfwMarkers.map((marker) => (
          <div
            key={marker.id}
            data-testid={`replay-gfw-${marker.id}`}
            className="absolute top-0 bottom-0 w-0.5 z-20"
            style={{
              left: `${marker.left}%`,
              backgroundColor: gfwTypeColors[marker.type] ?? '#6B7280',
            }}
            title={`GFW: ${marker.type.replace(/_/g, ' ')}`}
          />
        ))}

        {/* Progress indicator */}
        <div
          data-testid="replay-progress"
          className="absolute top-0 bottom-0 bg-blue-500/30 rounded-l z-0"
          style={{ width: `${progress}%` }}
        />

        {/* Playhead */}
        <div
          data-testid="replay-playhead"
          className="absolute top-0 bottom-0 w-0.5 bg-blue-400 z-30"
          style={{ left: `${progress}%` }}
        />
      </div>

      {/* Time labels */}
      <div className="flex justify-between text-xs text-gray-500">
        <span data-testid="replay-time-start">
          {formatTimestampAbsolute(trackStart)}
        </span>
        <span data-testid="replay-time-end">
          {formatTimestampAbsolute(trackEnd)}
        </span>
      </div>

      {/* Current point data */}
      {currentPoint && (
        <div data-testid="replay-current-data" className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <span className="text-gray-500">Time:</span>
            <div className="text-gray-300">{formatTimestampAbsolute(currentPoint.timestamp)}</div>
          </div>
          <div>
            <span className="text-gray-500">Speed:</span>
            <div className="text-gray-300">{formatSpeed(currentPoint.sog)}</div>
          </div>
          <div>
            <span className="text-gray-500">Course:</span>
            <div className="text-gray-300">{formatCourse(currentPoint.cog)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
