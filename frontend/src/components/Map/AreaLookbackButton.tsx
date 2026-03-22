import { useLookbackStore } from '../../hooks/useLookbackStore';

/** Button to activate area lookback drawing mode. */
export function AreaLookbackButton() {
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const isActive = useLookbackStore((s) => s.isActive);
  const startDrawing = useLookbackStore((s) => s.startDrawing);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);

  if (isActive) return null; // Don't show button during active lookback

  return (
    <button
      onClick={() => (isDrawing ? cancelDrawing() : startDrawing())}
      className={`flex items-center gap-1.5 px-2 py-1.5 rounded text-xs transition-colors border ${
        isDrawing
          ? 'bg-red-600 hover:bg-red-700 text-white border-red-500/30'
          : 'bg-[#0A0E17]/80 text-slate-400 hover:text-white hover:bg-[#111827]/90 border-[#1F2937]'
      }`}
      data-testid="area-lookback-button"
      aria-label={isDrawing ? 'Cancel drawing' : 'Area Lookback'}
    >
      {isDrawing ? 'Cancel Drawing' : 'Area Lookback'}
    </button>
  );
}
