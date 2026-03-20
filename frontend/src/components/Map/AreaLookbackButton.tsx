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
      className={`px-3 py-1.5 text-xs rounded transition-colors ${
        isDrawing
          ? 'bg-red-600 hover:bg-red-700 text-white'
          : 'bg-[#1F2937] hover:bg-[#374151] text-gray-300 hover:text-white border border-[#374151]'
      }`}
      data-testid="area-lookback-button"
      aria-label={isDrawing ? 'Cancel drawing' : 'Area Lookback'}
    >
      {isDrawing ? 'Cancel Drawing' : 'Area Lookback'}
    </button>
  );
}
