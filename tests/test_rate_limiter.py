"""Shared API admission must respect its limit under concurrent callers."""
import asyncio
from types import SimpleNamespace

import pytest

from cogs.utils import rate_limiter


async def test_concurrent_requests_respect_each_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0.0
    real_sleep = asyncio.sleep

    async def advance_clock(delay: float) -> None:
        nonlocal now
        wake_at = now + delay
        await real_sleep(0)
        now = max(now, wake_at)

    monkeypatch.setattr(rate_limiter, "time", SimpleNamespace(time=lambda: now, monotonic=lambda: now))
    monkeypatch.setattr(rate_limiter.asyncio, "sleep", advance_clock)
    limiter = rate_limiter.RateLimiter(requests_per_minute=2)
    admitted: list[float] = []

    async def request() -> None:
        await limiter.wait_if_needed()
        admitted.append(now)

    await asyncio.gather(*(request() for _ in range(7)))

    assert len(admitted) == 7
    assert all(sum(start <= timestamp < start + 60 for timestamp in admitted) <= 2 for start in admitted)
