"""_start_game must not leave a ghost reservation if Discord send fails."""
from __future__ import annotations

from unittest.mock import AsyncMock

import discord
import pytest

from cogs.crossword_cog.main import CrosswordCog

from .conftest import CORPUS, FakeAuthor, FakeBot, FakeChannel, build_game


class _Forbidden(discord.Forbidden):
    def __init__(self) -> None:
        Exception.__init__(self, "forbidden")


@pytest.mark.asyncio
async def test_failed_board_send_clears_active_game(seeded_random, monkeypatch) -> None:
    channel = FakeChannel(id=100)
    channel.send = AsyncMock(side_effect=_Forbidden())
    author = FakeAuthor(id=42, display_name="alice")
    bot = FakeBot()
    cog = CrosswordCog(bot)  # type: ignore[arg-type]
    cog._words = list(CORPUS)
    monkeypatch.setattr(
        "cogs.crossword_cog.main._build_game",
        lambda *_args, **_kwargs: build_game(),
    )

    err = await cog._start_game(channel, channel.id, author, "beginner", "es")

    assert err == "❌ Couldn't post the crossword. Try again!"
    assert channel.id not in cog._active
    assert bot.db.saved_active == []
