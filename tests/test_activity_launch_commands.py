"""Tests for the user-facing Activity launcher commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict, cast

import discord

from cogs.utils.activity_launch import ActivityLaunchView
from cogs.wordle_cog.main import WordleCog


class SentMessage(TypedDict):
    """Keyword arguments captured from a fake context send."""

    embed: discord.Embed
    view: discord.ui.View


@dataclass
class FakeContext:
    """Minimal command context that records sent messages."""

    sent: list[SentMessage] = field(default_factory=list)

    async def send(
        self,
        *,
        embed: discord.Embed,
        view: discord.ui.View,
    ) -> None:
        self.sent.append({"embed": embed, "view": view})


async def test_jaleo_posts_generic_activity_launcher() -> None:
    cog = WordleCog.__new__(WordleCog)
    ctx = FakeContext()

    assert cog.jaleo.name == "jaleo"
    # SAFETY: This assertion bridges a tested framework or fake-object type boundary.
    callback = cast(Any, cog.jaleo.callback)
    await callback(cog, ctx)

    assert len(ctx.sent) == 1
    embed = ctx.sent[0]["embed"]
    view = ctx.sent[0]["view"]
    assert isinstance(embed, discord.Embed)
    assert embed.title == "🎮 Juegos de Jaleo"
    assert "Wordle, Conjugación, Cloze" in (embed.description or "")
    assert isinstance(view, ActivityLaunchView)
    assert len(view.children) == 1
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.label == "Abrir Jaleo"
