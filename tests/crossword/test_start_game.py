"""_start_game must not leave a ghost reservation if Discord send fails."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.crossword_cog.config import MAX_WORD_LENGTH
from cogs.crossword_cog.main import CrosswordCog, _build_game

from .conftest import (
    CORPUS,
    FakeAuthor,
    FakeBot,
    FakeChannel,
    build_game,
    make_entry,
)


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
    assert bot.db.saved_active == []
    channel.send = AsyncMock(return_value=None)
    assert await cog._start_game(channel, channel.id, author, "beginner", "es") is None
    assert len(bot.db.saved_active) == 1


@pytest.mark.asyncio
async def test_slash_dm_start_uses_classic_embed(seeded_random, monkeypatch) -> None:
    channel = FakeChannel(id=100)
    channel.guild = None
    author = FakeAuthor(id=42, display_name="alice")
    bot = FakeBot()
    cog = CrosswordCog(bot)  # type: ignore[arg-type]
    cog._words = list(CORPUS)
    monkeypatch.setattr(
        "cogs.crossword_cog.main._build_game",
        lambda *_args, **_kwargs: build_game(),
    )
    monkeypatch.setattr(
        "cogs.crossword_cog.main._build_v2_view",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("v2 in DM")),
    )

    err = await cog._start_game(
        channel, channel.id, author, "beginner", "es", use_v2=True,
    )

    assert err is None
    assert "embed" in channel.sent[0]
    assert "view" not in channel.sent[0]


@pytest.mark.asyncio
async def test_snapshot_preserves_game_start(seeded_random, monkeypatch) -> None:
    channel = FakeChannel(id=100)
    author = FakeAuthor(id=42, display_name="alice")
    bot = FakeBot()
    cog = CrosswordCog(bot)  # type: ignore[arg-type]
    cog._words = list(CORPUS)
    game = build_game()
    game.started_at_wall = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("cogs.crossword_cog.main._build_game", lambda *_: game)
    assert await cog._start_game(channel, channel.id, author, "beginner", "es") is None
    assert bot.db.saved_active[0]["started_at"] == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_chart_without_data_only_replies() -> None:
    bot = FakeBot()
    bot.db.crossword_get_word_difficulty = AsyncMock(return_value=[])
    cog = CrosswordCog(bot)  # type: ignore[arg-type]
    ctx = AsyncMock()
    await CrosswordCog.cwchart.callback(cog, ctx)
    assert ctx.send.await_count == 1
    assert "Not enough per-word data" in ctx.send.call_args.args[0]
    assert ctx.send.call_args.kwargs == {}


@pytest.mark.asyncio
async def test_recovery_preserves_snapshot_start() -> None:
    bot = FakeBot()
    bot.fetch_user = AsyncMock()
    bot.db.crossword_record_interrupted = AsyncMock()
    cog = CrosswordCog(bot)  # type: ignore[arg-type]
    started = datetime(2026, 1, 1, tzinfo=UTC)
    await cog._notify_interrupted({
        "channel_id": 100, "starter_id": 42, "is_dm": True,
        "solved_count": 1, "total_words": 4, "language": "es",
        "difficulty": "beginner", "game_id": None, "guild_id": None,
        "started_at": started,
    })
    assert bot.db.crossword_record_interrupted.call_args.kwargs["started_at"] == started


def test_build_game_excludes_overlength_answers(monkeypatch) -> None:
    words = ["a" * MAX_WORD_LENGTH, "casa", "sala", "a" * (MAX_WORD_LENGTH + 1)]
    entries = [make_entry(word, "translation") for word in words]
    monkeypatch.setattr("cogs.crossword_cog.main.pick_words", lambda *_: entries)
    offered: list[list[str]] = []

    def cannot_place(answer_words: list[str]) -> None:
        offered.append(answer_words)

    monkeypatch.setattr("cogs.crossword_cog.main.generate_grid", cannot_place)
    assert _build_game(entries, "beginner", "es") is None
    assert offered
    assert all(answers == words[:3] for answers in offered)
