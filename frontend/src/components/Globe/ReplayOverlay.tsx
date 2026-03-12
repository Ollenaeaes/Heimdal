import { useMemo } from 'react';
import { Entity, PolylineGraphics, PointGraphics } from 'resium';
import { Cartesian3, Color } from 'cesium';
import type { ReplayGlobeState } from '../../hooks/useReplayStore';

interface ReplayOverlayProps {
  replay: ReplayGlobeState;
}

export function ReplayOverlay({ replay }: ReplayOverlayProps) {
  const { isActive, track, currentIndex, aisGaps } = replay;

  // Build the polyline positions from track
  const { normalSegments, gapSegments } = useMemo(() => {
    if (!track || track.length === 0) {
      return { normalSegments: [], gapSegments: [] };
    }

    // Identify gap index pairs
    const gapSet = new Set<string>();
    for (const gap of aisGaps) {
      gapSet.add(`${gap.startIndex}-${gap.endIndex}`);
    }

    // Build normal segments (blue) and gap segments (red)
    const normals: Cartesian3[][] = [];
    const gaps: Cartesian3[][] = [];

    let currentNormal: Cartesian3[] = [];

    for (let i = 0; i < track.length; i++) {
      const pt = Cartesian3.fromDegrees(track[i].lon, track[i].lat);

      if (i > 0 && gapSet.has(`${i - 1}-${i}`)) {
        // End current normal segment
        if (currentNormal.length > 0) {
          normals.push(currentNormal);
        }
        // Add gap segment
        const prevPt = Cartesian3.fromDegrees(track[i - 1].lon, track[i - 1].lat);
        gaps.push([prevPt, pt]);
        // Start new normal segment
        currentNormal = [pt];
      } else {
        currentNormal.push(pt);
      }
    }

    if (currentNormal.length > 0) {
      normals.push(currentNormal);
    }

    return { normalSegments: normals, gapSegments: gaps };
  }, [track, aisGaps]);

  // Current marker position
  const markerPosition = useMemo(() => {
    if (!track || track.length === 0 || currentIndex >= track.length) return null;
    const pt = track[currentIndex];
    return Cartesian3.fromDegrees(pt.lon, pt.lat);
  }, [track, currentIndex]);

  // Traversed path up to current index
  const traversedPositions = useMemo(() => {
    if (!track || track.length === 0) return [];
    const slice = track.slice(0, currentIndex + 1);
    return slice.map((pt) => Cartesian3.fromDegrees(pt.lon, pt.lat));
  }, [track, currentIndex]);

  if (!isActive || !track || track.length === 0) {
    return null;
  }

  return (
    <>
      {/* Full track polyline segments (dimmed blue) */}
      {normalSegments.map((positions, i) => (
        <Entity key={`replay-normal-${i}`}>
          <PolylineGraphics
            positions={positions}
            width={2}
            material={Color.fromCssColorString('#3B82F6').withAlpha(0.3)}
            clampToGround
          />
        </Entity>
      ))}

      {/* Gap segments (red dashed) */}
      {gapSegments.map((positions, i) => (
        <Entity key={`replay-gap-${i}`}>
          <PolylineGraphics
            positions={positions}
            width={2}
            material={Color.fromCssColorString('#DC2626').withAlpha(0.6)}
            clampToGround
          />
        </Entity>
      ))}

      {/* Traversed path (bright blue) */}
      {traversedPositions.length > 1 && (
        <Entity key="replay-traversed">
          <PolylineGraphics
            positions={traversedPositions}
            width={3}
            material={Color.fromCssColorString('#3B82F6').withAlpha(0.8)}
            clampToGround
          />
        </Entity>
      )}

      {/* Current position marker */}
      {markerPosition && (
        <Entity
          key="replay-marker"
          position={markerPosition}
          data-testid="replay-marker"
        >
          <PointGraphics
            pixelSize={12}
            color={Color.fromCssColorString('#60A5FA')}
            outlineColor={Color.WHITE}
            outlineWidth={2}
          />
        </Entity>
      )}
    </>
  );
}
