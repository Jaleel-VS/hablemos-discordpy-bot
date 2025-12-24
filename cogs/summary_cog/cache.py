"""
Simple cache for conversation summaries with TTL
"""
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SummaryCache:
    """In-memory cache for conversation summaries with TTL"""

    def __init__(self, ttl_seconds: int = 3600):  # Default 1 hour
        """
        Initialize the cache

        Args:
            ttl_seconds: Time to live for cached entries in seconds (default: 1 hour)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, dict] = {}
        self._stats = {
            'hits': 0,
            'misses': 0,
            'stores': 0,
            'evictions': 0
        }

    def _generate_cache_key(self, channel_id: int, message_id: int, count: int) -> str:
        """
        Generate unique cache key

        Args:
            channel_id: Discord channel ID
            message_id: Starting message ID
            count: Number of messages

        Returns:
            Cache key string
        """
        return f"{channel_id}:{message_id}:{count}"

    def get_summary(self, channel_id: int, message_id: int, count: int) -> Optional[str]:
        """
        Get cached summary

        Args:
            channel_id: Discord channel ID
            message_id: Starting message ID
            count: Number of messages

        Returns:
            Cached summary text or None if not found/expired
        """
        key = self._generate_cache_key(channel_id, message_id, count)
        return self.get(key)

    def set_summary(self, channel_id: int, message_id: int, count: int, summary: str) -> None:
        """
        Cache summary

        Args:
            channel_id: Discord channel ID
            message_id: Starting message ID
            count: Number of messages
            summary: Summary text to cache
        """
        key = self._generate_cache_key(channel_id, message_id, count)
        self.set(key, summary)

    def get(self, key: str) -> Optional[str]:
        """
        Get cached data for a key

        Args:
            key: The cache key

        Returns:
            Cached data or None if not found/expired
        """
        if key not in self._cache:
            self._stats['misses'] += 1
            return None

        entry = self._cache[key]
        age = time.time() - entry['timestamp']

        if age > self.ttl_seconds:
            # Expired entry, remove it
            del self._cache[key]
            self._stats['evictions'] += 1
            self._stats['misses'] += 1
            logger.debug(f"Cache entry expired for '{key}' (age: {age:.0f}s)")
            return None

        self._stats['hits'] += 1
        logger.debug(f"Cache hit for '{key}' (age: {age:.0f}s)")
        return entry['data']

    def set(self, key: str, data: str) -> None:
        """
        Store data in cache

        Args:
            key: The cache key
            data: The data to cache
        """
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
        self._stats['stores'] += 1
        logger.debug(f"Cached data for '{key}'")

    def clear(self) -> int:
        """
        Clear all cached entries

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared ({count} entries)")
        return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = []

        for key, entry in self._cache.items():
            age = current_time - entry['timestamp']
            if age > self.ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]
            self._stats['evictions'] += 1

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            **self._stats,
            'total_requests': total_requests,
            'hit_rate': hit_rate,
            'size': len(self._cache)
        }

    def get_size(self) -> int:
        """Get current number of cached entries"""
        return len(self._cache)
