"""Persistent UI views for the Language League cog."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Embed, Interaction, Member
from discord.ext import commands

if TYPE_CHECKING:
    from cogs.league_cog.main import LeagueCog

logger = logging.getLogger(__name__)


class LeagueJoinView(discord.ui.View):
    """Public, timeout-less join button for the Language League.

    Any member can click the button. The callback looks up ``LeagueCog`` at
    click time (so it survives cog reloads) and delegates to
    :meth:`LeagueCog.perform_join`, producing the same result as
    ``/league join``.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Join the League",
        style=discord.ButtonStyle.success,
        custom_id="league:join_button",
        emoji="🏆",
    )
    async def join_button(self, interaction: Interaction, _button: discord.ui.Button):
        try:
            cog = self.bot.get_cog("LeagueCog")
            if cog is None or not isinstance(interaction.user, Member):
                await interaction.response.send_message(
                    embed=Embed(
                        title="❌ Error",
                        description=(
                            "The Language League is not available right now. "
                            "Please try again in a moment."
                        ),
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
                return

            league_cog: LeagueCog = cog  # type: ignore[assignment]
            embed = await league_cog.perform_join(interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error("Error in league join button: %s", e, exc_info=True)
            error_embed = Embed(
                title="❌ Error",
                description="Failed to join Language League. Please try again later.",
                color=discord.Color.red(),
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
