"""$wordle — launch the Spanish Wordle Activity from a button.

Discord Activities are normally opened from the Activity Shelf (the 🚀 button),
which is hard to find. This cog gives players a discoverable entry point:
``$wordle`` posts a message with a button that launches the Activity directly
via the ``LAUNCH_ACTIVITY`` interaction response (discord.py 2.6+
``interaction.response.launch_activity()``).

Discord opens the Activity in the channel the button was clicked from (servers
and DMs are both valid contexts — no voice channel required).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

# How long the posted button stays clickable before Discord drops the
# interaction. Kept short since it's an on-demand, click-right-away button.
_VIEW_TIMEOUT = 180


class LaunchView(discord.ui.View):
    """A one-button view that launches the app's Activity when clicked."""

    def __init__(self) -> None:
        super().__init__(timeout=_VIEW_TIMEOUT)

    @discord.ui.button(label="Jugar Wordle", emoji="🎮", style=discord.ButtonStyle.primary)
    async def launch(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        try:
            # Launches the app's Activity in the channel this button was
            # clicked from. No message payload needed.
            await interaction.response.launch_activity()
        except discord.HTTPException as exc:
            logger.warning("launch_activity failed for user %s: %s", interaction.user.id, exc)
            msg = "No pude abrir el juego. Inténtalo de nuevo en un momento."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)


class WordleCog(BaseCog):
    """User-facing entry point to launch the Wordle Activity."""

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
        await ctx.send(embed=embed, view=LaunchView())


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(WordleCog(bot))
    logger.info("WordleCog loaded successfully")
