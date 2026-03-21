import { useVesselStore } from '../../hooks/useVesselStore';
import { SPEED_COLORS } from './TrackTrail';

/**
 * Speed color legend shown above the minimap when a vessel is selected.
 * Displays the speed-to-color mapping used for track trails.
 */
export function TrackLegend() {
  const selectedMmsi = useVesselStore((s) => s.selectedMmsi);

  if (selectedMmsi === null) return null;

  return (
    <div className="absolute bottom-[175px] left-3 z-30 bg-[#0A0E17]/85 backdrop-blur-sm border border-[#1F2937] rounded px-2.5 py-1.5">
      <div className="text-[0.6rem] text-slate-500 uppercase tracking-wider mb-1">
        Track Speed (kn)
      </div>
      <div className="flex items-center gap-0">
        {SPEED_COLORS.map((entry, i) => (
          <div key={entry.speed} className="flex flex-col items-center" style={{ width: 24 }}>
            <div
              className="w-full h-1.5"
              style={{
                backgroundColor: entry.color,
                borderRadius: i === 0 ? '2px 0 0 2px' : i === SPEED_COLORS.length - 1 ? '0 2px 2px 0' : 0,
              }}
            />
            <span className="text-[0.55rem] text-slate-400 font-mono mt-0.5">
              {entry.speed}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
