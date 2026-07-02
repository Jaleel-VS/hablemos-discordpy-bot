"""Catch-race test: the per-spawn lock must yield exactly one winner when
two players type `catch <word>` concurrently. Also covers the per-channel
mode routing (English-answer vs Spanish-answer)."""
import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from cogs.vocabcatch_cog.catch_logic import resolve_card
from cogs.vocabcatch_cog.config import (
    MODE_EN_TO_ES,
    MODE_ES_TO_EN,
    MODE_SHOW_ES,
)
from cogs.vocabcatch_cog.main import ActiveSpawn, ChannelState, VocabCatch

if TYPE_CHECKING:
    from cogs.vocabcatch_cog.renderer import Card
    from hablemos import Hablemos

CARD = {
    "card_id": 7, "word_es": "el relámpago", "word_en": "lightning",
    "part_of_speech": "sustantivo", "gender": "el",
    "example_es": "El relámpago iluminó el cielo.",
    "example_en": "The lightning lit the sky.", "rarity": 4,
}


class FakeDB:
    def __init__(self) -> None:
        self.catches: list[int] = []

    async def record_catch(self, user_id: int, card_id: int) -> int:
        self.catches.append(user_id)
        return 1


class FakeBot:
    def __init__(self) -> None:
        self.db = FakeDB()


def _make_message(user_id: int):
    author = SimpleNamespace(id=user_id, bot=False, display_name=f"U{user_id}")
    announced: list = []

    async def reply(*args, **kwargs):
        announced.append((args, kwargs))

    return SimpleNamespace(author=author, reply=reply, _announced=announced)


@pytest.fixture
def cog(monkeypatch):
    c = VocabCatch.__new__(VocabCatch)  # bypass __init__ (no real bot)
    c.bot = cast("Hablemos", FakeBot())  # test double
    c._channels = {}
    monkeypatch.setattr(
        "cogs.vocabcatch_cog.main.renderer.render_card",
        lambda card, view, *, revealed: __import__("io").BytesIO(b"x"))
    monkeypatch.setattr(
        "cogs.vocabcatch_cog.main.discord.File", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(
        "cogs.vocabcatch_cog.main.discord.Embed",
        lambda *a, **k: SimpleNamespace(set_image=lambda **kk: None,
                                        set_footer=lambda **kk: None))
    return c


def _spawn_state(mode: str) -> ChannelState:
    view = resolve_card(CARD, mode)
    state = ChannelState(mode=mode)
    state.active = ActiveSpawn(card=cast("Card", CARD), view=view, mode=mode,
                               message_id=1, spawned_at=0.0)
    return state


async def test_concurrent_catch_single_winner(cog) -> None:
    state = _spawn_state(MODE_SHOW_ES)
    m1, m2 = _make_message(111), _make_message(222)
    await asyncio.gather(
        cog._try_catch(m1, state, "relámpago"),
        cog._try_catch(m2, state, "el relampago"),
    )
    assert len(cog.bot.db.catches) == 1
    assert state.active is None
    assert len(m1._announced) + len(m2._announced) == 1


async def test_en_to_es_requires_spanish_answer(cog) -> None:
    # Beginner-EN shows English 'lightning'; catch by typing Spanish.
    state = _spawn_state(MODE_EN_TO_ES)
    m = _make_message(111)
    await cog._try_catch(m, state, "lightning")  # typing the prompt = wrong
    assert cog.bot.db.catches == []
    await cog._try_catch(m, state, "relámpago")  # Spanish answer = correct
    assert cog.bot.db.catches == [111]


async def test_es_to_en_requires_english_answer(cog) -> None:
    # Beginner-ES shows Spanish 'el relámpago'; catch by typing English.
    state = _spawn_state(MODE_ES_TO_EN)
    m = _make_message(111)
    await cog._try_catch(m, state, "relámpago")  # typing the prompt = wrong
    assert cog.bot.db.catches == []
    await cog._try_catch(m, state, "lightning")  # English answer = correct
    assert cog.bot.db.catches == [111]


async def test_wrong_guess_does_not_catch(cog) -> None:
    state = _spawn_state(MODE_SHOW_ES)
    m = _make_message(111)
    await cog._try_catch(m, state, "trueno")
    assert cog.bot.db.catches == []
    assert state.active is not None


async def test_catch_after_caught_is_noop(cog) -> None:
    state = _spawn_state(MODE_SHOW_ES)
    assert state.active is not None
    state.active.caught = True
    m = _make_message(111)
    await cog._try_catch(m, state, "relámpago")
    assert cog.bot.db.catches == []
