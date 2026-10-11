"""Spotify now-playing is opt-in: activity is only read for opted-in members."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.spotify_cog.main import SpotifyCog
from cogs.spotify_cog.views import OptInView


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
async def test_not_opted_in_self_gets_an_opt_in_button() -> None:
    target = _NoActivities(1)
    ctx = _ctx(author_id=1, target=target)

    result = await _cog(opted_in=False)._listening_target(ctx, None)

    assert result is None
    kwargs = ctx.send.await_args.kwargs
    assert isinstance(kwargs["view"], OptInView)
    assert "anyone in the server" in kwargs["embed"].description
    assert "$spotify off" in kwargs["embed"].description


@pytest.mark.asyncio
async def test_not_opted_in_other_member_is_not_read() -> None:
    target = _NoActivities(2)
    ctx = _ctx(author_id=1, target=target)

    result = await _cog(opted_in=False)._listening_target(ctx, cast(Any, target))

    assert result is None
    kwargs = ctx.send.await_args.kwargs
    assert "hasn't turned on Spotify sharing" in kwargs["embed"].description
    assert "view" not in kwargs  # a member can't opt in someone else


@pytest.mark.asyncio
async def test_opted_in_member_returns_activity() -> None:
    spotify = MagicMock(spec=discord.Spotify)
    target = SimpleNamespace(id=2, display_name="member2", activities=[spotify])
    ctx = _ctx(author_id=1, target=target)

    result = await _cog(opted_in=True)._listening_target(ctx, cast(Any, target))

    assert result == (target, spotify)
    ctx.send.assert_not_awaited()


def _view(*, optin: AsyncMock | None = None) -> tuple[OptInView, MagicMock, AsyncMock]:
    optin = optin or AsyncMock(return_value=True)
    bot = SimpleNamespace(db=SimpleNamespace(spotify_optin=optin))
    ctx = _ctx(author_id=1, target=None)
    ctx.reinvoke = AsyncMock()
    return OptInView(cast(Any, bot), ctx), ctx, optin


def _interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user = SimpleNamespace(id=user_id)
    interaction.response.edit_message = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


@pytest.mark.asyncio
async def test_button_opts_in_the_requester_and_reruns_the_command() -> None:
    view, ctx, optin = _view()
    interaction = _interaction(user_id=1)

    await view.opt_in.callback(interaction)

    optin.assert_awaited_once_with(1)
    ctx.reinvoke.assert_awaited_once()
    assert all(item.disabled for item in view.children)
    assert "now **on**" in interaction.response.edit_message.await_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_button_is_refused_for_anyone_but_the_requester() -> None:
    view, ctx, optin = _view()
    interaction = _interaction(user_id=2)

    assert await view.interaction_check(interaction) is False

    interaction.response.send_message.assert_awaited_once()
    optin.assert_not_awaited()
    ctx.reinvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_opt_in_does_not_rerun_the_command() -> None:
    view, ctx, _ = _view(optin=AsyncMock(side_effect=RuntimeError("db down")))
    interaction = _interaction(user_id=1)

    await view.opt_in.callback(interaction)

    ctx.reinvoke.assert_not_awaited()
    interaction.response.edit_message.assert_not_awaited()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_card_failure_after_opt_in_is_reported_not_raised() -> None:
    view, ctx, optin = _view()
    ctx.reinvoke.side_effect = RuntimeError("render failed")
    interaction = _interaction(user_id=1)

    await view.opt_in.callback(interaction)

    optin.assert_awaited_once_with(1)
    assert "Sharing is on" in interaction.followup.send.await_args.kwargs["embed"].description
