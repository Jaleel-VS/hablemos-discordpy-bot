"""Higher-or-Lower pair selection and view construction."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.hol_cog.config import HOL_CHANNEL_IDS
from cogs.hol_cog.data import TERMS, pick_pair
from cogs.hol_cog.main import GameView, HigherOrLower


def test_pick_pair_excludes_seen_terms() -> None:
    exclude = {term for term, _vol in TERMS[:-2]}
    remaining = {term for term, _vol in TERMS[-2:]}
    known, _kv, mystery, _mv = pick_pair(exclude)
    assert {known, mystery} == remaining


def test_pick_pair_raises_when_fewer_than_two_remain() -> None:
    exclude = {term for term, _vol in TERMS[1:]}
    with pytest.raises(ValueError, match="not enough unused terms"):
        pick_pair(exclude)


def test_chained_view_keeps_selected_round_not_a_fresh_pair() -> None:
    cog = SimpleNamespace(_active={})
    player = SimpleNamespace(id=7)
    seen = {"ChatGPT", "YouTube", "WhatsApp"}
    view = GameView(
        cast(Any, cog),
        cast(Any, player),
        known="YouTube",
        known_vol=1,
        mystery="WhatsApp",
        mystery_vol=2,
        streak=3,
        seen=seen,
    )
    assert view.known == "YouTube"
    assert view.mystery == "WhatsApp"
    assert view.streak == 3
    assert view.seen is seen


class _Forbidden(discord.Forbidden):
    def __init__(self) -> None:
        Exception.__init__(self, "forbidden")


@pytest.mark.asyncio
async def test_failed_hol_send_clears_active_game() -> None:
    ctx = SimpleNamespace(
        author=SimpleNamespace(id=7),
        channel=SimpleNamespace(id=HOL_CHANNEL_IDS[0]),
        send=AsyncMock(side_effect=_Forbidden()),
    )
    cog = HigherOrLower(cast(Any, SimpleNamespace()))
    cog._active = {}

    await HigherOrLower.hol.callback(cog, ctx)

    assert 7 not in cog._active
