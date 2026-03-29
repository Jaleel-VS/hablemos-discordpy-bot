"""Introduce cog — slash command for member introductions and exchange partner requests."""
import logging

import discord
from discord import Embed, Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog

from .config import COMMAND_CHANNEL_ID, INTRODUCTIONS_CHANNEL_ID
from .views import IntroStartView

logger = logging.getLogger(__name__)


class IntroduceCog(BaseCog):
    """Cog for member introductions and language exchange partner requests."""

    @app_commands.command(
        name="introduce",
        description="Introduce yourself to the community",
    )
    async def introduce(self, interaction: Interaction):
        """Start the introduction flow."""
        if interaction.channel_id != COMMAND_CHANNEL_ID:
            command_channel = interaction.client.get_channel(COMMAND_CHANNEL_ID)
            channel_mention = command_channel.mention if command_channel else f"<#{COMMAND_CHANNEL_ID}>"
            await interaction.response.send_message(
                f"This command can only be used in {channel_mention}.",
                ephemeral=True,
            )
            return

        view = IntroStartView(introductions_channel_id=INTRODUCTIONS_CHANNEL_ID)
        embed = Embed(
            title="Introduction",
            description=(
                "Welcome! Let's introduce you to the community.\n\n"
                "Are you looking for a language exchange partner?"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="This form will expire in 5 minutes")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        logger.info("Introduction started by user %s", interaction.user.id)


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(IntroduceCog(bot))
    logger.info("IntroduceCog loaded")
