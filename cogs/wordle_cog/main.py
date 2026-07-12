"""$wordle — launch the Spanish Wordle Activity from a button.

Discord Activities are normally opened from the Activity Shelf (the 🚀 button),
which is hard to find. This cog gives players a discoverable entry point:
``$wordle`` posts a message with a button that launches the Activity. The launch
opens the one embedded app; with more than one game registered the app shows its
hub, so this button lands on the game menu (the ``LAUNCH_ACTIVITY`` callback has
no deep-link parameter — see ``cogs/utils/activity_launch.py``).
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


class WordleCog(BaseCog):
    """User-facing entry point to launch the Activity (Wordle-themed)."""

    @commands.command(name="wordle", aliases=["palabra"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def wordle(self, ctx: commands.Context) -> None:
        """Post a button that launches the Spanish Wordle Activity."""
        embed = discord.Embed(
            title="🟩 Wordle en español",
            description=(
                "Adivina la palabra del día en 6 intentos.\n\n"
                "Pulsa el botón para jugar."
            ),
            color=0x3AA394,
        )
        view = ActivityLaunchView(label="Jugar Wordle", emoji="🎮")
        await ctx.send(embed=embed, view=view)


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(WordleCog(bot))
    logger.info("WordleCog loaded successfully")
