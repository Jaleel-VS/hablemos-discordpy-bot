"""Spotify now-playing is opt-in: activity is only read for opted-in members."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.spotify_cog.main import SpotifyCog


class _NoActivities:
    """Member stand-in whose activities must not be read."""

    def __init__(self, member_id: int) -> None:
        self.id = member_id
        self.display_name = f"member{member_id}"

    @property
    def activities(self) -> Any:
        raise AssertionError("activities read for a member who has not opted in")


def _cog(opted_in: bool) -> SpotifyCog:
    db = SimpleNamespace(is_spotify_opted_in=AsyncMock(return_value=opted_in))
    return SpotifyCog(cast(Any, SimpleNamespace(db=db)))


def _ctx(author_id: int, target: Any) -> MagicMock:
    ctx = MagicMock()
    ctx.author = SimpleNamespace(id=author_id)
    ctx.guild = SimpleNamespace(get_member=lambda _member_id: target)
    ctx.send = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_not_opted_in_self_is_told_how_to_enable() -> None:
    target = _NoActivities(1)
    ctx = _ctx(author_id=1, target=target)

    result = await _cog(opted_in=False)._listening_target(ctx, None)

    assert result is None
    embed = ctx.send.await_args.kwargs["embed"]
    assert "$spotify on" in embed.description


@pytest.mark.asyncio
async def test_not_opted_in_other_member_is_not_read() -> None:
    target = _NoActivities(2)
    ctx = _ctx(author_id=1, target=target)

    result = await _cog(opted_in=False)._listening_target(ctx, cast(Any, target))

    assert result is None
    embed = ctx.send.await_args.kwargs["embed"]
    assert "hasn't turned on Spotify sharing" in embed.description


@pytest.mark.asyncio
async def test_opted_in_member_returns_activity() -> None:
    spotify = MagicMock(spec=discord.Spotify)
    target = SimpleNamespace(id=2, display_name="member2", activities=[spotify])
    ctx = _ctx(author_id=1, target=target)

    result = await _cog(opted_in=True)._listening_target(ctx, cast(Any, target))

    assert result == (target, spotify)
    ctx.send.assert_not_awaited()
