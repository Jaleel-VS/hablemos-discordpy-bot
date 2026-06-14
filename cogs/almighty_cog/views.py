"""Persistent UI for the Almighty cog (working title).

``TriggerView`` is a timeout-less button posted in the trigger channel.
Pressing it opens ``SubmissionModal``; on submit, the form contents are
relayed as an embed to the feed channel. Write in one channel, read in
another.
"""
from __future__ import annotations

import logging

import discord
from discord import Color, Embed, Interaction, TextStyle
from discord.ext import commands
from discord.ui import Modal, TextInput

from cogs.utils.embeds import red_embed

from .config import FEED_CHANNEL_ID

logger = logging.getLogger(__name__)


class SubmissionModal(Modal, title="New submission"):
    """Collects a short form and relays it to the feed channel."""

    subject: TextInput = TextInput(
        label="Subject",
        placeholder="A short title…",
        max_length=100,
        required=True,
    )
    details: TextInput = TextInput(
        label="Details",
        style=TextStyle.paragraph,
        placeholder="Write the details here…",
        max_length=1500,
        required=True,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: Interaction) -> None:
        # Acknowledge first so the modal always closes within Discord's 3s
        # window, even if the feed post is slow or fails. We edit this
        # ephemeral message afterwards to report the real outcome.
        await interaction.response.send_message(
            embed=Embed(description="⏳ Submitting…", color=Color.blurple()),
            ephemeral=True,
        )

        feed = self.bot.get_channel(FEED_CHANNEL_ID)
        if not isinstance(feed, discord.abc.Messageable):
            logger.error("Almighty feed channel %s unavailable", FEED_CHANNEL_ID)
            await interaction.edit_original_response(
                embed=red_embed("The feed channel is unavailable right now. Try again later."),
            )
            return

        embed = Embed(
            title=str(self.subject.value),
            description=str(self.details.value),
            color=Color.blurple(),
            timestamp=interaction.created_at,
        )
        user = interaction.user
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_footer(text=f"Submitted by {user} • {user.id}")

        try:
            await feed.send(embed=embed)
        except discord.Forbidden:
            logger.error("Missing permissions to post in Almighty feed channel %s", FEED_CHANNEL_ID)
            await interaction.edit_original_response(
                embed=red_embed("I can't post in the feed channel. Ask an admin to check my permissions."),
            )
            return
        except discord.HTTPException as exc:
            logger.error("Failed to relay Almighty submission: %s", exc, exc_info=True)
            await interaction.edit_original_response(
                embed=red_embed("Something went wrong sending your submission. Try again later."),
            )
            return

        await interaction.edit_original_response(
            embed=Embed(description="✅ Submitted!", color=Color.green()),
        )

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        # Backstop: any unhandled error in on_submit lands here. Make sure
        # the interaction is acknowledged so the user never sees a silent
        # "interaction failed" with the modal stuck open.
        logger.error("Almighty submission modal error: %s", error, exc_info=True)
        message = red_embed("Something went wrong. Please try again later.")
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=message)
            else:
                await interaction.response.send_message(embed=message, ephemeral=True)
        except discord.HTTPException:
            pass


class TriggerView(discord.ui.View):
    """Persistent (timeout-less) button that opens the submission form."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Submit",
        style=discord.ButtonStyle.primary,
        custom_id="almighty:submit",
        emoji="📝",
    )
    async def submit_button(self, interaction: Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(SubmissionModal(self.bot))
