"""$conjuga — launch the Spanish conjugation Activity from a button.

Companion to ``$wordle``: a discoverable entry point that posts a button which
launches the embedded Activity. Both commands open the same one app; with
multiple games registered the app shows its hub, so this button lands on the
game menu (the ``LAUNCH_ACTIVITY`` callback carries no deep-link parameter — see
``cogs/utils/activity_launch.py`` for the full explanation).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.activity_launch import ActivityLaunchView

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class ConjugaCog(BaseCog):
    """User-facing entry point to launch the Activity (conjugation-themed)."""

    @commands.command(name="conjuga", aliases=["conjugar"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def conjuga(self, ctx: commands.Context) -> None:
        """Post a button that launches the conjugation Activity."""
        embed = discord.Embed(
            title="↻ Conjugación en español",
            description=(
                "Conjuga tantos verbos como puedas en 60 segundos.\n\n"
                "Pulsa el botón para jugar."
            ),
            color=0x5865F2,
        )
        view = ActivityLaunchView(label="Jugar Conjugación", emoji="🎮")
        await ctx.send(embed=embed, view=view)


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(ConjugaCog(bot))
    logger.info("ConjugaCog loaded successfully")
