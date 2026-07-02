"""Integration tests for CrosswordCog.on_message.

Uses the fake bot / channel / message harness in conftest.py. No real
Discord or DB is touched. These tests target the lock-protected paths
and concurrency semantics introduced when the per-game timeout tasks
were replaced with a global watcher.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import pytest

from .conftest import FakeAuthor, FakePermissions, make_message

if TYPE_CHECKING:
    import discord

    from .conftest import FakeDB


async def test_correct_answer_awards_and_bumps_db(cog_with_game) -> None:
    cog, game, channel = cog_with_game
    answer = game.grid.placed[0].word
    author = FakeAuthor(id=42, display_name="alice")
    msg = make_message(channel, author, answer)

    await cog.on_message(msg)

    assert 0 in game.solved
    assert game.solvers[0] == "alice"
    assert game.solver_ids[0] == 42
    assert cog.bot.db.bump_calls == [channel.id]
    assert "✅" in msg.reactions


async def test_wrong_single_word_gets_x_reaction(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "zyxwvu")
    await cog.on_message(msg)
    assert "❌" in msg.reactions


async def test_wrong_multi_word_no_reaction(cog_with_game) -> None:
    """A sentence shouldn't get an ❌ — it's probably just chat."""
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "hola que tal")
    await cog.on_message(msg)
    assert "❌" not in msg.reactions


async def test_guess_too_long_is_silent(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "a" * 60)
    await cog.on_message(msg)
    assert msg.reactions == []


async def test_quit_as_starter_ends_game(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "quit")
    await cog.on_message(msg)
    assert channel.id not in cog._active
    assert channel.id not in cog._locks
    assert cog.bot.db.clear_calls == [channel.id]
    # One "cancelled" message should have been sent to the channel.
    assert any("cancelled" in (s.get("content") or "") for s in channel.sent)


async def test_quit_as_non_starter_without_perms_noop(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(999, "bob"), "quit")
    await cog.on_message(msg)
    # Game still active.
    assert channel.id in cog._active


async def test_quit_as_mod_ends_game(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    channel._perms = FakePermissions(manage_messages=True)
    msg = make_message(channel, FakeAuthor(999, "mod"), "quit")
    await cog.on_message(msg)
    assert channel.id not in cog._active


async def test_ignores_bot_messages(cog_with_game) -> None:
    cog, game, channel = cog_with_game
    answer = game.grid.placed[0].word
    bot_author = FakeAuthor(1, "some-bot", bot=True)
    msg = make_message(channel, bot_author, answer)
    await cog.on_message(msg)
    assert 0 not in game.solved


async def test_hint_command(cog_with_game) -> None:
    cog, game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "!hint")
    await cog.on_message(msg)
    assert "💡" in msg.reactions
    assert game.hints_used == 1


async def test_third_hint_blocked_with_denied_reaction(cog_with_game) -> None:
    cog, game, channel = cog_with_game
    game.hints_used = 2
    msg = make_message(channel, FakeAuthor(42, "alice"), "!hint")
    await cog.on_message(msg)
    assert "🚫" in msg.reactions


# --------------------------------------------------------------------------- #
# Concurrency: these exercise the per-channel lock added in _get_lock.        #
# --------------------------------------------------------------------------- #

async def test_simultaneous_solvers_credit_only_one(cog_with_game) -> None:
    """Two users send the same correct answer concurrently. The lock
    must serialize them so only the first is credited and the DB is
    bumped exactly once."""
    cog, game, channel = cog_with_game
    answer = game.grid.placed[0].word
    m1 = make_message(channel, FakeAuthor(1, "alice"), answer)
    m2 = make_message(channel, FakeAuthor(2, "bob"), answer)

    await asyncio.gather(cog.on_message(m1), cog.on_message(m2))

    assert len(game.solvers) == 1
    assert cog.bot.db.bump_calls == [channel.id]
    # Exactly one ✅ reaction total across the two messages.
    total_check = sum(r.count("✅") for r in (m1.reactions, m2.reactions))
    assert total_check == 1


async def test_simultaneous_quit_and_solve_no_double_end(cog_with_game) -> None:
    """A solve racing a quit must not cause two completions. Either the
    quit wins (game cancelled) or the solve wins (game still going or
    completed), never both."""
    cog, game, channel = cog_with_game
    answer = game.grid.placed[0].word
    quitter = make_message(channel, FakeAuthor(42, "alice"), "quit")
    solver = make_message(channel, FakeAuthor(2, "bob"), answer)

    await asyncio.gather(cog.on_message(quitter), cog.on_message(solver))

    # DB clear should happen at most once.
    assert len(cog.bot.db.clear_calls) <= 1
    # Game must be removed exactly once.
    assert channel.id not in cog._active
    assert channel.id not in cog._locks


async def test_timeout_watcher_vs_solve_one_end_only(
    fake_bot, fake_channel, seeded_random, monkeypatch,
) -> None:
    """Force the watcher to tick immediately and race a solver. Only one
    of them should end the game; the other must see ``_active`` already
    empty under the lock and bail."""
    from cogs.crossword_cog.main import CrosswordCog

    fake_bot._channels[fake_channel.id] = fake_channel
    cog = CrosswordCog(fake_bot)  # type: ignore[arg-type]

    from .conftest import build_game
    game = build_game()
    game.channel_id = fake_channel.id
    game.starter_id = 42
    # Make the game instantly timed-out.
    game.started_at -= 10_000
    cog._active[fake_channel.id] = game
    cog._timeout_override = 1  # any positive; game is already 10000s old

    # Simulate a single watcher tick by running the same body inline —
    # we don't want a 30s sleep in the test.
    async def one_watcher_tick() -> None:
        import time
        now = time.monotonic()
        timeout = cog._timeout_override or 1
        to_end = [
            cid for cid, g in cog._active.items()
            if now - g.started_at > timeout
        ]
        for channel_id in to_end:
            lock = cog._get_lock(channel_id)
            async with lock:
                g = cog._active.get(channel_id)
                if g is None:
                    continue
                await cog._end_game(channel_id, completed=False)

    answer = game.grid.placed[0].word
    solver = make_message(
        fake_channel, FakeAuthor(2, "bob"), answer,
    )

    await asyncio.gather(
        one_watcher_tick(),
        cog.on_message(cast("discord.Message", solver)),  # test double
    )

    # Regardless of who won, the cog must end up with no active game
    # and exactly one cleanup of the DB active-game row.
    assert fake_channel.id not in cog._active
    assert fake_channel.id not in cog._locks
    assert len(cast("FakeDB", cog.bot.db).clear_calls) == 1


async def test_completion_flow_end_to_end(cog_with_game) -> None:
    """Solve every word in order and verify the game ends cleanly."""
    cog, game, channel = cog_with_game
    total = len(game.grid.placed)
    for i in range(total):
        answer = game.grid.placed[i].word
        msg = make_message(channel, FakeAuthor(42, "alice"), answer)
        await cog.on_message(msg)
    assert channel.id not in cog._active
    assert len(cog.bot.db.bump_calls) == total
    # Outcome was persisted exactly once.
    assert len(cog.bot.db.persisted) == 1
    assert cog.bot.db.persisted[0]["completion"] == "completed"


async def test_lock_is_cleaned_up_after_quit(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "quit")
    await cog.on_message(msg)
    assert channel.id not in cog._locks


async def test_many_games_lock_leak_check(
    fake_bot, seeded_random,
) -> None:
    """1000 start→quit cycles must not leave orphaned locks behind."""
    from cogs.crossword_cog.main import CrosswordCog

    from .conftest import FakeChannel, build_game

    cog = CrosswordCog(fake_bot)  # type: ignore[arg-type]
    for i in range(1000):
        ch = FakeChannel(id=10_000 + i)
        fake_bot._channels[ch.id] = ch
        game = build_game()
        game.channel_id = ch.id
        game.starter_id = 42
        cog._active[ch.id] = game
        msg = make_message(ch, FakeAuthor(42, "alice"), "quit")
        await cog.on_message(cast("discord.Message", msg))  # test double
    assert len(cog._active) == 0
    assert len(cog._locks) == 0


@pytest.mark.parametrize("text", ["", " ", "a"])
async def test_short_or_empty_input_silent(cog_with_game, text) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), text)
    await cog.on_message(msg)
    assert msg.reactions == []
