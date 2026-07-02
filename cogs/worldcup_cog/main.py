"""World Cup cog — slash command to self-assign a team role."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Interaction, app_commands

from base_cog import BaseCog

from .views import WorldCupMenuView

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class WorldCup(BaseCog):
    """Self-service team role picker for World Cup 2026."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)

    @app_commands.command(name="worldcup", description="Manage your World Cup team role")
    @app_commands.guild_only()
    async def worldcup(self, interaction: Interaction) -> None:
        """Show the World Cup team menu."""
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        teams = sorted(
            [r for r in guild.roles if r.name.startswith("Team ")],
            key=lambda r: r.name,
        )

        if not teams:
            await interaction.response.send_message(
                "No team roles are configured yet. Ask a staff member to set them up.",
                ephemeral=True,
            )
            return

        current_team = next((r for r in member.roles if r.name.startswith("Team ")), None)

        view = WorldCupMenuView(teams=teams, user_id=member.id, current_team=current_team)
        await interaction.response.send_message(
            "What would you like to do?",
            view=view,
            ephemeral=True,
        )


async def setup(bot: Hablemos) -> None:
    await bot.add_cog(WorldCup(bot))
