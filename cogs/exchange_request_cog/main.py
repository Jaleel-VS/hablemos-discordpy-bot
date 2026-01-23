import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed
from base_cog import BaseCog
import logging

from .config import CHANNELS
from .views import ExchangeRequestView

logger = logging.getLogger(__name__)


class ExchangeRequestCog(BaseCog):
    """Cog for managing language exchange partner requests."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @app_commands.command(
        name="exchange_request",
        description="Create a language exchange partner request"
    )
    async def exchange_request(self, interaction: Interaction):
        """Start the exchange partner request flow."""
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
        view = ExchangeRequestView(results_channel_id=CHANNELS.RESULTS_CHANNEL)

        # Create the initial embed
        embed = Embed(
            title="Exchange Partner Request (Step 1/3)",
            description=(
                "Looking for a language exchange partner? Fill out this form!\n\n"
                "**Step 1:** Select the languages you offer and are looking for."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="This form will expire in 5 minutes")

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
        logger.info(f"Exchange request started by {interaction.user} ({interaction.user.id})")


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(ExchangeRequestCog(bot))
    logger.info("ExchangeRequestCog loaded successfully")
