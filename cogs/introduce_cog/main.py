import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed
from base_cog import BaseCog
import logging

from .config import CHANNELS
from .views import IntroStartView

logger = logging.getLogger(__name__)


class IntroduceCog(BaseCog):
    """Cog for member introductions and language exchange partner requests."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @app_commands.command(
        name="introduce",
        description="Introduce yourself to the community"
    )
    async def introduce(self, interaction: Interaction):
        """Start the introduction flow."""
        # Check if command is used in the correct channel
        if interaction.channel_id != CHANNELS.COMMAND_CHANNEL:
            command_channel = interaction.client.get_channel(CHANNELS.COMMAND_CHANNEL)
            channel_mention = command_channel.mention if command_channel else f"<#{CHANNELS.COMMAND_CHANNEL}>"
            await interaction.response.send_message(
                f"This command can only be used in {channel_mention}.",
                ephemeral=True
            )
            return

        # Create the initial view
        view = IntroStartView(introductions_channel_id=CHANNELS.INTRODUCTIONS_CHANNEL)

        # Create the initial embed
        embed = Embed(
            title="Introduction (Step 1/4)",
            description=(
                "Welcome! Let's introduce you to the community.\n\n"
                "**Step 1:** Are you looking for a language exchange partner?"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="This form will expire in 5 minutes")

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
        logger.info(f"Introduction started by {interaction.user} ({interaction.user.id})")


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(IntroduceCog(bot))
    logger.info("IntroduceCog loaded successfully")
