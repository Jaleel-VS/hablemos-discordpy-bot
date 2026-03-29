"""Introduce cog — slash and prefix commands for member introductions and exchange partner requests."""
import logging

import discord
from discord import ButtonStyle, Embed, Interaction, app_commands
from discord.ext import commands
from discord.ui import Button, View, button

from base_cog import BaseCog

from .config import COMMAND_CHANNEL_ID, INTRODUCTIONS_CHANNEL_ID
from .views import IntroStartView

logger = logging.getLogger(__name__)


def _intro_embed() -> Embed:
    """Build the intro start embed."""
    embed = Embed(
        title="Introduction",
        description=(
            "Welcome! Let's introduce you to the community.\n\n"
            "Are you looking for a language exchange partner?"
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="This form will expire in 5 minutes")
    return embed


async def _start_intro_flow(interaction: Interaction) -> None:
    """Send the ephemeral intro start view."""
    view = IntroStartView(introductions_channel_id=INTRODUCTIONS_CHANNEL_ID)
    await interaction.response.send_message(embed=_intro_embed(), view=view, ephemeral=True)
    logger.info("Introduction started by user %s", interaction.user.id)


class IntroduceButton(View):
    """Persistent button that kicks off the introduction flow."""

    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Introduce Yourself", style=ButtonStyle.primary, custom_id="introduce:start", emoji="👋")
    async def start_button(self, interaction: Interaction, btn: Button):
        """Handle button click — start the ephemeral intro flow."""
        await _start_intro_flow(interaction)


class IntroduceCog(BaseCog):
    """Introduce yourself and find language exchange partners."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        bot.add_view(IntroduceButton())

    @app_commands.command(
        name="introduce",
        description="Introduce yourself to the community",
    )
    async def introduce_slash(self, interaction: Interaction):
        """Start the introduction flow via slash command."""
        if interaction.channel_id != COMMAND_CHANNEL_ID:
            command_channel = interaction.client.get_channel(COMMAND_CHANNEL_ID)
            channel_mention = command_channel.mention if command_channel else f"<#{COMMAND_CHANNEL_ID}>"
            await interaction.response.send_message(
                f"This command can only be used in {channel_mention}.",
                ephemeral=True,
            )
            return

        await _start_intro_flow(interaction)

    @commands.command(name="introduce")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def introduce_prefix(self, ctx: commands.Context):
        """Send a persistent button to start the introduction flow."""
        if ctx.channel.id != COMMAND_CHANNEL_ID:
            command_channel = ctx.bot.get_channel(COMMAND_CHANNEL_ID)
            channel_mention = command_channel.mention if command_channel else f"<#{COMMAND_CHANNEL_ID}>"
            await ctx.send(f"This command can only be used in {channel_mention}.")
            return

        embed = Embed(
            title="👋 Introduce Yourself",
            description="Click the button below to introduce yourself to the community!",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, view=IntroduceButton())


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(IntroduceCog(bot))
    logger.info("IntroduceCog loaded")
