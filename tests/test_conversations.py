"""Daily $convo quota is reserved atomically and refundable."""
from __future__ import annotations

from typing import Any

import pytest

from db.conversations import ConversationsMixin


class _Recorder(ConversationsMixin):
    def __init__(self, fetchval: Any = 1) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetchval_query: str | None = None
        self.fetchval_args: tuple[Any, ...] = ()
        self._fetchval_result = fetchval

    def _pool(self):  # pragma: no cover - unused by overrides
        raise RuntimeError("not used")

    async def _fetchval(self, query: str, *args: Any):
        self.fetchval_query = query
        self.fetchval_args = args
        return self._fetchval_result

    async def _execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_try_reserve_daily_usage_returns_true_when_row_returned() -> None:
    db = _Recorder(fetchval=1)
    assert await db.try_reserve_daily_usage(7, 2) is True
    assert db.fetchval_query is not None
    assert "ON CONFLICT (user_id) DO UPDATE" in db.fetchval_query
    assert "conversation_count < $2" in db.fetchval_query
    assert db.fetchval_args == (7, 2)


@pytest.mark.asyncio
async def test_try_reserve_daily_usage_returns_false_when_at_limit() -> None:
    db = _Recorder(fetchval=None)
    assert await db.try_reserve_daily_usage(7, 2) is False


@pytest.mark.asyncio
async def test_refund_daily_usage_decrements_today_only() -> None:
    db = _Recorder()
    await db.refund_daily_usage(7)
    query, args = db.executed[0]
    assert "conversation_count = conversation_count - 1" in query
    assert "date = CURRENT_DATE" in query
    assert args == (7,)
