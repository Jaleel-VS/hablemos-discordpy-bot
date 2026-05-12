"""World Cup cog — slash command to self-assign a team role."""
import logging

from discord import Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog

from .views import TeamSelectView

logger = logging.getLogger(__name__)


class WorldCup(BaseCog):
    """Self-service team role picker for World Cup 2026."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    @app_commands.command(name="equipo", description="Elige el equipo que vas a apoyar en el Mundial")
    @app_commands.guild_only()
    async def equipo(self, interaction: Interaction) -> None:
        """Show a paginated select menu of World Cup team roles."""
        guild = interaction.guild
        teams = sorted(
            [r for r in guild.roles if r.name.startswith("Team ")],
            key=lambda r: r.name,
        )

        if not teams:
            await interaction.response.send_message(
                "No hay roles de equipos configurados todavía. Pídele a un staff que los cree.",
                ephemeral=True,
            )
            return

        view = TeamSelectView(teams=teams, user_id=interaction.user.id)
        await interaction.response.send_message(
            "Selecciona tu equipo del Mundial:",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WorldCup(bot))
