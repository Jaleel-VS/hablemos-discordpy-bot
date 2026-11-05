"""Activity result and statistics rendering contracts."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.activity_results_cog.main import ActivityResultsCog


@pytest.mark.asyncio
@pytest.mark.parametrize("distribution", [{"3": 2, "X": 1}, '{"3": 2, "X": 1}'])
async def test_user_stats_preserve_distribution_and_backend_label(distribution):
    db = SimpleNamespace(
        activity_user_stats=AsyncMock(return_value={
            "games": 3, "wins": 2, "current_streak": 1,
            "max_streak": 2, "distribution": distribution,
        }),
        activity_game_label=AsyncMock(return_value="Phrasal Verbs"),
    )
    cog = object.__new__(ActivityResultsCog)
    cog.bot = SimpleNamespace(db=db)
    ctx = SimpleNamespace(send=AsyncMock())
    member = SimpleNamespace(id=42, mention="<@42>", display_name="Learner")

    await ActivityResultsCog.activity_stats_user.callback(cog, ctx, member, "phrasal")

    embed = ctx.send.call_args.kwargs["embed"]
    assert embed.title == "Phrasal Verbs · Learner"
    assert "Distribución: 3: 2 · X: 1" in embed.description
    assert "Partidas: **3** · Victorias: **2**" in embed.description
