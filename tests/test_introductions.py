"""Duplicate introductions must not extend the accepted cooldown."""
from __future__ import annotations

from typing import Any

import pytest

from db.introductions import IntroductionsMixin


class _Recorder(IntroductionsMixin):
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetched: list[tuple[str, tuple[Any, ...]]] = []

    def _pool(self):  # pragma: no cover - unused by overrides
        raise RuntimeError("not used")

    async def _execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "INSERT 0 1"

    async def _fetchrow(self, query: str, *args: Any):
        self.fetched.append((query, args))
        return None


@pytest.mark.asyncio
async def test_record_introduction_defaults_to_accepted() -> None:
    db = _Recorder()
    assert await db.record_introduction(7) is True
    query, args = db.executed[0]
    assert "accepted" in query
    assert args == (7, True)


@pytest.mark.asyncio
async def test_record_duplicate_introduction_is_not_accepted() -> None:
    db = _Recorder()
    assert await db.record_introduction(7, accepted=False) is True
    _query, args = db.executed[0]
    assert args == (7, False)


@pytest.mark.asyncio
async def test_check_user_introduction_filters_accepted_rows() -> None:
    db = _Recorder()
    await db.check_user_introduction(7, 90)
    query, args = db.fetched[0]
    assert "AND accepted" in query
    assert args == (7, 90)
