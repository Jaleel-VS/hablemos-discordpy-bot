"""Shared stubs and factories for crossword tests.

These tests never touch Discord or PostgreSQL. They exercise the cog's
pure logic (grid generation, normalize, try_solve, use_hint) and, for
the on_message integration tests, wire the cog up to fake bot / message
/ channel objects that record interactions so we can assert on them.

The fakes deliberately implement only what the crossword cog actually
calls. If a test fails with ``AttributeError`` on a fake, add the
missing method here rather than pulling in a mocking library.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from cogs.crossword_cog.grid import generate_grid
from cogs.crossword_cog.main import CrosswordCog, CrosswordGame
from cogs.crossword_cog.words import WordEntry

# --------------------------------------------------------------------------- #
# Word / game factories                                                       #
# --------------------------------------------------------------------------- #

def make_entry(
    word_es: str,
    word_en: str,
    clue_es: str = "clue-es",
    clue_en: str = "clue-en",
    theme: str = "test",
    difficulty: str = "beginner",
) -> WordEntry:
    return WordEntry(
        word_es=word_es,
        word_en=word_en,
        clue_es=clue_es,
        clue_en=clue_en,
        theme=theme,
        difficulty=difficulty,
    )


# A small fixed corpus used by most tests. Chosen to cross cleanly so
# generate_grid succeeds deterministically (given the seed in the
# `seeded_random` fixture).
CORPUS: list[WordEntry] = [
    make_entry("casa", "house"),
    make_entry("sol", "sun"),
    make_entry("luna", "moon"),
    make_entry("agua", "water"),
    make_entry("cancion", "song"),   # intentionally unaccented storage
]


def build_game(
    entries: list[WordEntry] | None = None,
    *,
    language: str = "es",
    difficulty: str = "beginner",
) -> CrosswordGame:
    """Build a CrosswordGame with a real generated grid.

    Raises if the grid can't be placed — tests rely on the corpus being
    placeable, so a failure here is a genuine regression.
    """
    entries = entries if entries is not None else CORPUS
    answer_words = [e.word_es if language == "es" else e.word_en for e in entries]
    grid = generate_grid(answer_words)
    assert grid is not None, "test corpus failed to generate a grid"

    # Align entries with grid.placed order (generate_grid sorts by length).
    ordered: list[WordEntry] = []
    used: set[int] = set()
    for pw in grid.placed:
        for j, aw in enumerate(answer_words):
            if j not in used and aw == pw.word:
                ordered.append(entries[j])
                used.add(j)
                break

    return CrosswordGame(grid, ordered, language, difficulty)


# --------------------------------------------------------------------------- #
# Fake Discord objects                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class FakePermissions:
    manage_messages: bool = False


@dataclass
class FakeAuthor:
    id: int
    display_name: str
    bot: bool = False

    def __str__(self) -> str:
        return self.display_name


@dataclass
class FakeChannel:
    id: int
    sent: list[dict] = field(default_factory=list)
    _perms: FakePermissions = field(default_factory=FakePermissions)

    async def send(self, content: str | None = None, **kwargs: Any) -> FakeMessage:
        record = {"content": content, **kwargs}
        self.sent.append(record)
        msg = FakeMessage(
            channel=self,
            author=FakeAuthor(id=0, display_name="bot", bot=True),
            content=content or "",
        )
        return msg

    def permissions_for(self, _author: Any) -> FakePermissions:
        return self._perms


@dataclass
class FakeMessage:
    channel: FakeChannel
    author: FakeAuthor
    content: str
    reactions: list[str] = field(default_factory=list)

    async def add_reaction(self, emoji: str) -> None:
        self.reactions.append(emoji)


@dataclass
class FakeContext:
    valid: bool = False


class FakeDB:
    """Records DB calls; returns sensible defaults."""

    def __init__(self) -> None:
        self.bump_calls: list[int] = []
        self.clear_calls: list[int] = []
        self.persisted: list[dict] = []
        self.pool = None  # not used by tests that bypass cog_load

    async def crossword_bump_solved(self, channel_id: int) -> None:
        self.bump_calls.append(channel_id)

    async def crossword_clear_active_game(self, channel_id: int) -> None:
        self.clear_calls.append(channel_id)

    async def crossword_persist_game_outcome(self, **kwargs: Any) -> None:
        self.persisted.append(kwargs)

    async def crossword_get_all_active_games(self) -> list[dict]:
        return []

    async def crossword_record_interrupted(self, **kwargs: Any) -> None:
        pass


class FakeBot:
    """Minimal stand-in for commands.Bot.

    Only implements what CrosswordCog.on_message and _end_game touch.
    """

    def __init__(self, channels: dict[int, FakeChannel] | None = None) -> None:
        self.db = FakeDB()
        self._channels = channels or {}

    async def get_context(self, _message: Any) -> FakeContext:
        return FakeContext(valid=False)

    def get_channel(self, channel_id: int) -> FakeChannel | None:
        return self._channels.get(channel_id)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def seeded_random() -> None:
    """Deterministic randomness for tests that hit grid / hint RNG."""
    import random
    random.seed(1234)


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def fake_channel() -> FakeChannel:
    return FakeChannel(id=100)


@pytest.fixture
def author() -> FakeAuthor:
    return FakeAuthor(id=42, display_name="alice")


@pytest.fixture
async def cog_with_game(
    fake_bot: FakeBot, fake_channel: FakeChannel, seeded_random: None,
) -> tuple[CrosswordCog, CrosswordGame, FakeChannel]:
    """A cog wired to a fake bot with one active game in ``fake_channel``.

    ``cog_load`` is deliberately *not* called — we don't want to hit the
    DB word loader or start the global timeout watcher.
    """
    fake_bot._channels[fake_channel.id] = fake_channel
    cog = CrosswordCog(fake_bot)  # type: ignore[arg-type]
    game = build_game()
    game.channel_id = fake_channel.id
    game.starter_id = 42
    cog._active[fake_channel.id] = game
    return cog, game, fake_channel


def make_message(
    channel: FakeChannel, author: FakeAuthor, content: str,
) -> FakeMessage:
    return FakeMessage(channel=channel, author=author, content=content)


async def run_all(*coros: Any) -> list[Any]:
    """asyncio.gather with exceptions surfaced, for race tests."""
    return await asyncio.gather(*coros, return_exceptions=False)
