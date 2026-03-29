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

    async def wait_if_needed(self):
        """Wait if we're at rate limit."""
        now = time.time()
        self.requests = [r for r in self.requests if now - r < 60]

        if len(self.requests) >= self.rpm:
            oldest = self.requests[0]
            wait_time = 60 - (now - oldest) + 0.5
            if wait_time > 0:
                logger.info("Rate limit reached, waiting %.1fs", wait_time)
                await asyncio.sleep(wait_time)

        self.requests.append(time.time())
