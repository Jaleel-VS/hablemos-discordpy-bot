"""Introduce cog — slash and prefix commands for member introductions.

Language-exchange partner finding now lives in ``langex_cog``; this cog
is introductions only.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import ButtonStyle, Embed, Interaction, app_commands
from discord.ext import commands
from discord.ui import Button, View, button

from base_cog import BaseCog

from .config import (
    COMMAND_CHANNEL_ID,
    INTRODUCTIONS_CHANNEL_ID,
    detect_ui_lang,
)
from .modals import IntroOnlyModal

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


async def _start_intro_flow(interaction: Interaction) -> None:
    """Open the introduction modal directly (intro-only, no exchange branch)."""
    lang = detect_ui_lang(interaction.user) if isinstance(interaction.user, discord.Member) else "en"
    await interaction.response.send_modal(
        IntroOnlyModal(introductions_channel_id=INTRODUCTIONS_CHANNEL_ID, lang=lang),
    )
    logger.info("Introduction started by user %s", interaction.user.id)


class IntroduceButton(View):
    """Persistent button that kicks off the introduction flow."""

    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Introduce Yourself", style=ButtonStyle.primary, custom_id="introduce:start", emoji="👋")
    async def start_button(self, interaction: Interaction, btn: Button):
        await _start_intro_flow(interaction)


class IntroduceCog(BaseCog):
    """Introduce yourself to the community."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        bot.add_view(IntroduceButton())

    # ── /introduce ──

    @app_commands.command(name="introduce", description="Introduce yourself to the community")
    async def introduce_slash(self, interaction: Interaction):
        if interaction.channel_id != COMMAND_CHANNEL_ID:
            ch = interaction.client.get_channel(COMMAND_CHANNEL_ID)
            mention = ch.mention if isinstance(ch, discord.abc.GuildChannel) else f"<#{COMMAND_CHANNEL_ID}>"
            await interaction.response.send_message(f"Use this in {mention}.", ephemeral=True)
            return
        await _start_intro_flow(interaction)

    @commands.command(name="introduce")
    async def introduce_prefix(self, ctx: commands.Context):
        """Post the persistent 'Introduce Yourself' button in the current channel."""
        embed = Embed(
            title="👋 Introduce Yourself",
            description="Press the button below to introduce yourself to the community.",
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, view=IntroduceButton())


async def setup(bot: Hablemos):
    await bot.add_cog(IntroduceCog(bot))
    logger.info("IntroduceCog loaded")
