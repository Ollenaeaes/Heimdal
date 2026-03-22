import { useLookbackStore } from '../../hooks/useLookbackStore';
import { useMenuClose } from '../Controls/MenuDropdown';

/** Button to activate area lookback drawing mode. */
export function AreaLookbackButton() {
  const isDrawing = useLookbackStore((s) => s.isDrawing);
  const isActive = useLookbackStore((s) => s.isActive);
  const startDrawing = useLookbackStore((s) => s.startDrawing);
  const cancelDrawing = useLookbackStore((s) => s.cancelDrawing);
  const closeMenu = useMenuClose();

  if (isActive) return null;

  const handleClick = () => {
    if (isDrawing) {
      cancelDrawing();
    } else {
      startDrawing();
    }
    closeMenu?.();
  };

  return (
    <button
      onClick={handleClick}
      className={`w-full text-left px-3 py-1.5 text-xs rounded transition-colors ${
        isDrawing
          ? 'bg-red-600/20 text-red-400'
          : 'text-slate-300 hover:bg-[#1F2937] hover:text-white'
      }`}
      data-testid="area-lookback-button"
    >
      {isDrawing ? 'Cancel Drawing' : 'Area Lookback'}
    </button>
  );
}
