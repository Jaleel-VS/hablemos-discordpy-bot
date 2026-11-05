"""Shared rate limiter for API calls."""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API calls."""

    def __init__(self, requests_per_minute: int = 15):
        self.rpm = requests_per_minute
        self.requests: list[float] = []
        self._lock = asyncio.Lock()

    async def wait_if_needed(self):
        """Wait if we're at rate limit."""
        async with self._lock:
            now = time.monotonic()
            self.requests = [r for r in self.requests if now - r < 60]
            if len(self.requests) >= self.rpm:
                wait_time = 60 - (now - self.requests[0]) + 0.5
                logger.info("Rate limit reached, waiting %.1fs", wait_time)
                await asyncio.sleep(wait_time)
                now = time.monotonic()
                self.requests = [r for r in self.requests if now - r < 60]
            self.requests.append(now)
