"""Integration tests for CrosswordCog.on_message.

Uses the fake bot / channel / message harness in conftest.py. No real
Discord or DB is touched. These tests target the lock-protected paths
and concurrency semantics introduced when the per-game timeout tasks
were replaced with a global watcher.
"""
from __future__ import annotations

import asyncio

import pytest

from cogs.crossword_cog.config import MAX_WORD_LENGTH

from .conftest import FakeAuthor, FakePermissions, make_message


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


@pytest.mark.parametrize("length, reacts", [(MAX_WORD_LENGTH, True), (MAX_WORD_LENGTH + 1, False)])
async def test_wrong_guess_feedback_word_limit(cog_with_game, length, reacts) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "z" * length)
    await cog.on_message(msg)
    assert ("❌" in msg.reactions) is reacts


async def test_quit_as_starter_ends_game(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), "quit")
    await cog.on_message(msg)
    later = make_message(channel, FakeAuthor(42, "alice"), "casa")
    await cog.on_message(later)
    assert later.reactions == []
    assert cog.bot.db.clear_calls == [channel.id]
    assert any("cancelled" in (s.get("content") or "") for s in channel.sent)


async def test_quit_as_non_starter_without_perms_noop(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(999, "bob"), "quit")
    await cog.on_message(msg)
    answer = make_message(channel, FakeAuthor(42, "alice"), "casa")
    await cog.on_message(answer)
    assert "✅" in answer.reactions


async def test_quit_as_mod_ends_game(cog_with_game) -> None:
    cog, _game, channel = cog_with_game
    channel._perms = FakePermissions(manage_messages=True)
    msg = make_message(channel, FakeAuthor(999, "mod"), "quit")
    await cog.on_message(msg)
    assert "👋" in msg.reactions
    assert cog.bot.db.persisted[0]["completion"] == "quit"


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

    assert cog.bot.db.clear_calls == [channel.id]
    assert len(cog.bot.db.persisted) == 1
    assert cog.bot.db.persisted[0]["completion"] == "quit"


async def test_timeout_watcher_vs_solve_one_end_only(
    fake_bot, fake_channel, seeded_random, monkeypatch,
) -> None:
    """A real watcher tick racing a solve must persist one timeout."""
    from cogs.crossword_cog.main import CrosswordCog

    fake_bot._channels[fake_channel.id] = fake_channel
    cog = CrosswordCog(fake_bot)  # type: ignore[arg-type]

    from .conftest import build_game
    game = build_game()
    game.channel_id = fake_channel.id
    game.starter_id = 42
    game.started_at -= 10_000
    cog._active[fake_channel.id] = game
    cog._timeout_override = 1

    original_sleep = asyncio.sleep
    ticked = asyncio.Event()

    async def controlled_sleep(_seconds: float) -> None:
        if ticked.is_set():
            raise asyncio.CancelledError
        ticked.set()
        await original_sleep(0)

    monkeypatch.setattr("cogs.crossword_cog.main.asyncio.sleep", controlled_sleep)

    answer = game.grid.placed[0].word
    solver = make_message(
        fake_channel, FakeAuthor(2, "bob"), answer,
    )

    await asyncio.gather(cog._global_timeout_watcher(), cog.on_message(solver))
    assert fake_bot.db.clear_calls == [fake_channel.id]
    assert len(fake_bot.db.persisted) == 1
    assert fake_bot.db.persisted[0]["completion"] == "timeout"
    later = make_message(fake_channel, FakeAuthor(2, "bob"), answer)
    await cog.on_message(later)
    assert later.reactions == []


async def test_completion_flow_end_to_end(cog_with_game) -> None:
    """Solve every word in order and verify the game ends cleanly."""
    cog, game, channel = cog_with_game
    total = len(game.grid.placed)
    for i in range(total):
        answer = game.grid.placed[i].word
        msg = make_message(channel, FakeAuthor(42, "alice"), answer)
        await cog.on_message(msg)
    later = make_message(channel, FakeAuthor(42, "alice"), game.grid.placed[0].word)
    await cog.on_message(later)
    assert later.reactions == []
    assert len(cog.bot.db.bump_calls) == total
    assert len(cog.bot.db.persisted) == 1
    assert cog.bot.db.persisted[0]["completion"] == "completed"


async def test_hinted_word_is_persisted_as_hinted(cog_with_game) -> None:
    cog, game, channel = cog_with_game
    await cog.on_message(make_message(channel, FakeAuthor(42, "alice"), "!hint"))
    for placed in game.grid.placed:
        await cog.on_message(make_message(channel, FakeAuthor(42, "alice"), placed.word))
    events = cog.bot.db.persisted[0]["word_events"]
    assert [event["had_hint"] for event in events].count(True) == 1


@pytest.mark.parametrize("text", ["", " ", "a"])
async def test_short_or_empty_input_silent(cog_with_game, text) -> None:
    cog, _game, channel = cog_with_game
    msg = make_message(channel, FakeAuthor(42, "alice"), text)
    await cog.on_message(msg)
    assert msg.reactions == []
