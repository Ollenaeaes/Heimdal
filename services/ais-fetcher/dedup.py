"""In-memory deduplication for the AIS fetcher.

Simple set-based dedup that resets every hour.  No Redis dependency.
A restart during the same hour may re-write some messages — that's fine
because the batch-pipeline loader handles duplicates via ON CONFLICT.
"""

from __future__ import annotations

import time


class InMemoryDedup:
    """Lightweight in-memory dedup using a set, reset hourly."""

    def __init__(self):
        self._seen: set[str] = set()
        self._current_hour: int = self._get_hour()

    @staticmethod
    def _get_hour() -> int:
        return int(time.time()) // 3600

    def is_duplicate(self, mmsi: int, timestamp_str: str) -> bool:
        """Check if this (mmsi, timestamp) pair was seen this hour."""
        hour = self._get_hour()
        if hour != self._current_hour:
            self._seen.clear()
            self._current_hour = hour

        # Round timestamp to the second for dedup
        ts_key = timestamp_str[:19] if timestamp_str else ""
        key = f"{mmsi}:{ts_key}"

        if key in self._seen:
            return True
        self._seen.add(key)
        return False
