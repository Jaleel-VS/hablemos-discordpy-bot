"""
Simple text-based cache for synonym/antonym lookups
"""
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SynonymCache:
    """In-memory cache for synonym/antonym data with TTL"""

    def __init__(self, ttl_seconds: int = 86400):  # Default 24 hours
        """
        Initialize the cache

        Args:
            ttl_seconds: Time to live for cached entries in seconds (default: 24 hours)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, dict] = {}
        self._stats = {
            'hits': 0,
            'misses': 0,
            'stores': 0,
            'evictions': 0
        }

    def get(self, word: str) -> Optional[Dict]:
        """
        Get cached data for a word

        Args:
            word: The word to lookup

        Returns:
            Cached data dict or None if not found/expired
        """
        word = word.lower().strip()

        if word not in self._cache:
            self._stats['misses'] += 1
            return None

        entry = self._cache[word]
        age = time.time() - entry['timestamp']

        if age > self.ttl_seconds:
            # Expired entry, remove it
            del self._cache[word]
            self._stats['evictions'] += 1
            self._stats['misses'] += 1
            logger.debug(f"Cache entry expired for '{word}' (age: {age:.0f}s)")
            return None

        self._stats['hits'] += 1
        logger.debug(f"Cache hit for '{word}' (age: {age:.0f}s)")
        return entry['data']

    def set(self, word: str, data: Dict) -> None:
        """
        Store data in cache

        Args:
            word: The word key
            data: The data to cache
        """
        word = word.lower().strip()
        self._cache[word] = {
            'data': data,
            'timestamp': time.time()
        }
        self._stats['stores'] += 1
        logger.debug(f"Cached data for '{word}'")

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
        expired_words = []

        for word, entry in self._cache.items():
            age = current_time - entry['timestamp']
            if age > self.ttl_seconds:
                expired_words.append(word)

        for word in expired_words:
            del self._cache[word]
            self._stats['evictions'] += 1

        if expired_words:
            logger.info(f"Cleaned up {len(expired_words)} expired cache entries")

        return len(expired_words)

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
