import { useWatchlistStore, useWatchlistMutations } from '../../hooks/useWatchlist';

interface WatchButtonProps {
  mmsi: number;
}

export function WatchButton({ mmsi }: WatchButtonProps) {
  const isWatched = useWatchlistStore((s) => s.watchedMmsis.has(mmsi));
  const { addMutation, removeMutation } = useWatchlistMutations();

  const handleClick = () => {
    if (isWatched) {
      removeMutation.mutate({ mmsi });
    } else {
      addMutation.mutate({ mmsi });
    }
  };

  const isPending = addMutation.isPending || removeMutation.isPending;

  return (
    <button
      data-testid="watch-button"
      onClick={handleClick}
      disabled={isPending}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
        isWatched
          ? 'bg-blue-600/20 text-blue-400 hover:bg-blue-600/30'
          : 'bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white'
      } disabled:opacity-50`}
      aria-label={isWatched ? 'Unwatch vessel' : 'Watch vessel'}
    >
      <span className="text-sm">{isWatched ? '⊙' : '⊙'}</span>
      {isWatched ? 'Unwatch' : 'Watch'}
    </button>
  );
}
