"""Modals for the Introduce cog — free-text input forms."""
import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import Embed, Interaction, TextStyle
from discord.ui import Modal, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import EXCHANGE_COLOR, INTRO_COLOR

if TYPE_CHECKING:
    from .views import ExchangeRequestView

logger = logging.getLogger(__name__)


def _format_as_list(text: str) -> str:
    """Format comma- or newline-separated text as a bulleted list."""
    separator = '\n' if '\n' in text else ','
    items = [item.strip() for item in text.split(separator) if item.strip()]
    if len(items) <= 1:
        return text.strip()
    return '\n'.join(f"• {item}" for item in items)


def _format_blockquote(text: str) -> str:
    """Format text as a Discord blockquote."""
    return '\n'.join(f"> {line}" for line in text.strip().split('\n'))


async def _post_introduction(
    interaction: Interaction,
    embed: Embed,
    channel_id: int,
    success_message: str,
) -> None:
    """Shared logic: fetch channel, post embed, confirm to user."""
    await interaction.response.defer(ephemeral=True)

    channel = interaction.client.get_channel(channel_id)
    if not channel:
        try:
            channel = await interaction.client.fetch_channel(channel_id)
        except discord.NotFound:
            logger.error("Introductions channel %s not found", channel_id)
            await interaction.followup.send(embed=red_embed("Introductions channel not found. Please contact an admin."), ephemeral=True)
            return
        except discord.HTTPException:
            logger.exception("Failed to fetch introductions channel %s", channel_id)
            await interaction.followup.send(embed=red_embed("Could not reach the introductions channel. Please try again later."), ephemeral=True)
            return

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        logger.error("Missing permissions to post in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed("I don't have permission to post in the introductions channel."), ephemeral=True)
        return
    except discord.HTTPException:
        logger.exception("Failed to post introduction in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed("Failed to post your introduction. Please try again later."), ephemeral=True)
        return

    await interaction.followup.send(
        embed=green_embed(f"Your introduction has been posted to {channel.mention}.\n\n{success_message}"),
        ephemeral=True,
    )
    logger.info("Introduction posted by user %s", interaction.user.id)


class IntroOnlyModal(Modal, title="Introduce Yourself"):
    """Modal for simple introduction without exchange partner details."""

    about_me = TextInput(
        label="About Me",
        placeholder="Tell others a bit about yourself...",
        required=True,
        max_length=500,
        style=TextStyle.paragraph,
    )

    interests = TextInput(
        label="Your Interests (Optional)",
        placeholder="e.g., Watching YouTube, sports, music, cooking, gaming...",
        required=False,
        max_length=500,
        style=TextStyle.paragraph,
    )

    def __init__(self, introductions_channel_id: int):
        super().__init__()
        self.introductions_channel_id = introductions_channel_id

    async def on_submit(self, interaction: Interaction):
        embed = Embed(
            title="New Member Introduction",
            description=f"**{interaction.user.mention}** has joined the community!",
            color=INTRO_COLOR,
        )
        embed.add_field(name="About Me", value=self.about_me.value.strip(), inline=False)

        interests = (self.interests.value or "").strip()
        if interests:
            embed.add_field(name="My Interests", value=_format_as_list(interests), inline=False)

        if interaction.user.avatar:
            embed.set_thumbnail(url=interaction.user.avatar.url)

        await _post_introduction(interaction, embed, self.introductions_channel_id, "Welcome to the community!")


class ExchangeDetailsModal(Modal, title="Exchange Partner Details"):
    """Modal for collecting free-text details about the exchange request."""

    about_me = TextInput(
        label="About Me",
        placeholder="Tell others a bit about yourself...",
        required=True,
        max_length=500,
        style=TextStyle.paragraph,
    )

    activities = TextInput(
        label="Activities You'd Like To Do (Optional)",
        placeholder="e.g., Watch shows together, voice calls, text chat, play games...",
        required=False,
        max_length=500,
        style=TextStyle.paragraph,
    )

    additional_info = TextInput(
        label="Additional Info (Optional)",
        placeholder="Age/age range, availability, dialect preference, etc.",
        required=False,
        max_length=500,
        style=TextStyle.paragraph,
    )

    def __init__(self, parent_view: ExchangeRequestView, introductions_channel_id: int):
        super().__init__()
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id

    async def on_submit(self, interaction: Interaction):
        embed = self._build_request_embed(interaction.user)
        await _post_introduction(interaction, embed, self.introductions_channel_id, "Good luck finding a partner!")

    def _build_request_embed(self, user: discord.User | discord.Member) -> Embed:
        """Build the formatted embed for exchange partner requests."""
        pv = self.parent_view

        about_me_text = _format_blockquote(self.about_me.value.strip())
        embed = Embed(
            description=f"{user.mention}'s seeking an exchange partner!\n\n**About Me**\n{about_me_text}",
            color=EXCHANGE_COLOR,
        )

        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        embed.set_author(name=user.display_name, icon_url=avatar_url)

        # What I Offer
        embed.add_field(name="Language", value=pv.language_offering_display, inline=True)
        embed.add_field(name="Level", value=pv.offering_level_display, inline=True)
        current_unix = int(time.time())
        embed.add_field(name="Timezone", value=f"{pv.timezone} — <t:{current_unix}:t>", inline=True)

        # What I Want
        embed.add_field(
            name="⭐ What I want",
            value="-# What I'm looking for in a language partner and how we can practice together.",
            inline=False,
        )
        embed.add_field(name="Language", value=pv.language_seeking_display, inline=True)
        embed.add_field(name="Level", value=pv.seeking_level_display, inline=True)
        country_value = pv.country_display if pv.country and pv.country != "no_preference" else "No preference"
        embed.add_field(name="Country", value=country_value, inline=True)

        # Optional free-text fields
        activities = (self.activities.value or "").strip()
        if activities:
            embed.add_field(name="Activities", value=_format_blockquote(activities), inline=False)

        additional = (self.additional_info.value or "").strip()
        if additional:
            embed.add_field(name="Additional Information", value=_format_blockquote(additional), inline=False)

        footer = "Please send me DM if you want to be my language partner!" if pv.prefer_dm else "Please tag me in the server if you want to be my language partner!"
        embed.set_footer(text=footer)

        return embed
