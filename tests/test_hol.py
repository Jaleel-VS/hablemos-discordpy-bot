"""Higher-or-Lower pair selection and view construction."""
from __future__ import annotations

from types import SimpleNamespace
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


@pytest.mark.asyncio
async def test_chained_round_uses_previous_mystery_and_advances_streak(monkeypatch) -> None:
    cog = HigherOrLower(SimpleNamespace())
    player = SimpleNamespace(id=7)
    view = GameView(
        cog, player, known="YouTube", known_vol=1,
        mystery="WhatsApp", mystery_vol=2, streak=3,
        seen={"ChatGPT", "YouTube", "WhatsApp"},
    )
    monkeypatch.setattr("cogs.hol_cog.main.pick_pair", lambda _seen: ("unused", 0, "Reddit", 10))
    interaction = SimpleNamespace(
        response=SimpleNamespace(edit_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    await view.higher.callback(interaction)
    result = interaction.response.edit_message.call_args.kwargs["embed"]
    assert "Streak: 4" in result.title
    round_embed = interaction.followup.send.call_args.kwargs["embed"]
    assert "**WhatsApp**" in round_embed.description
    assert "**Reddit**" in round_embed.description
    assert "Streak: 4" in round_embed.title


class _Forbidden(discord.Forbidden):
    def __init__(self) -> None:
        Exception.__init__(self, "forbidden")


@pytest.mark.asyncio
async def test_failed_hol_send_allows_a_new_game() -> None:
    ctx = SimpleNamespace(
        author=SimpleNamespace(id=7),
        channel=SimpleNamespace(id=HOL_CHANNEL_IDS[0]),
        send=AsyncMock(side_effect=_Forbidden()),
    )
    cog = HigherOrLower(SimpleNamespace())
    await HigherOrLower.hol.callback(cog, ctx)
    ctx.send.reset_mock(side_effect=True)
    await HigherOrLower.hol.callback(cog, ctx)
    ctx.send.assert_awaited_once()
    assert ctx.send.call_args.kwargs["embed"].title.startswith("🎮 Higher or Lower?")
