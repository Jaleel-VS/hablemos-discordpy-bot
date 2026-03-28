"""Simple in-memory cache for conversation summaries with TTL."""
import logging
import time

logger = logging.getLogger(__name__)


class SummaryCache:
    """In-memory cache for conversation summaries with TTL."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, dict] = {}
        self._stats = {'hits': 0, 'misses': 0, 'stores': 0, 'evictions': 0}

    def _key(self, channel_id: int, start_id: int, end_id: int) -> str:
        return f"{channel_id}:{start_id}:{end_id}"

    def get(self, channel_id: int, start_id: int, end_id: int) -> str | None:
        """Get cached summary, or None if missing/expired."""
        key = self._key(channel_id, start_id, end_id)
        entry = self._cache.get(key)

        if entry is None:
            self._stats['misses'] += 1
            return None

        if time.time() - entry['ts'] > self.ttl_seconds:
            del self._cache[key]
            self._stats['evictions'] += 1
            self._stats['misses'] += 1
            return None

        self._stats['hits'] += 1
        return entry['data']

    def set(self, channel_id: int, start_id: int, end_id: int, summary: str) -> None:
        """Cache a summary."""
        key = self._key(channel_id, start_id, end_id)
        self._cache[key] = {'data': summary, 'ts': time.time()}
        self._stats['stores'] += 1

    def clear(self) -> int:
        """Clear all entries. Returns count removed."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> dict:
        total = self._stats['hits'] + self._stats['misses']
        return {
            **self._stats,
            'total_requests': total,
            'hit_rate': (self._stats['hits'] / total * 100) if total else 0,
            'size': len(self._cache),
        }
