"""Hangman start-command validation."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.hangman_cog.main import HangmanController


@pytest.mark.asyncio
async def test_invalid_category_resets_cooldown() -> None:
    ctx = SimpleNamespace(
        channel=SimpleNamespace(id=1),
        author=SimpleNamespace(id=2),
        send=AsyncMock(),
    )
    calls: list[str] = []
    cog = SimpleNamespace(
        hangman=SimpleNamespace(reset_cooldown=lambda _ctx: calls.append("reset")),
    )

    await HangmanController.hangman.callback(cog, ctx, category="animles")

    assert calls == ["reset"]
    ctx.send.assert_awaited_once()
    assert "Category not found" in ctx.send.await_args.args[0]


@pytest.mark.asyncio
async def test_failed_start_does_not_reraise() -> None:
    ctx = SimpleNamespace(
        channel=SimpleNamespace(id=1),
        author=SimpleNamespace(id=2),
        send=AsyncMock(),
    )
    lock = asyncio.Lock()
    cog = SimpleNamespace(
        active_games={},
        _get_channel_lock=lambda _id: lock,
        _is_game_active=lambda _id: False,
        _start_new_game=AsyncMock(side_effect=RuntimeError("boom")),
    )

    await HangmanController.hangman.callback(cog, ctx, category="animales")

    ctx.send.assert_awaited_once()
    assert "Failed to start game" in ctx.send.await_args.args[0]
    assert 1 not in cog.active_games
