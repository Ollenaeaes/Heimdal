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
      className={`w-full text-left px-3 py-1.5 text-xs rounded transition-colors ${
        isDrawing
          ? 'bg-red-600 hover:bg-red-700 text-white'
          : 'text-slate-300 hover:bg-[#1F2937] hover:text-white'
      }`}
      data-testid="area-lookback-button"
      aria-label={isDrawing ? 'Cancel drawing' : 'Area Lookback'}
    >
      {isDrawing ? 'Cancel Drawing' : 'Area Lookback'}
    </button>
  );
}
