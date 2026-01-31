from __future__ import annotations

import discord
from discord.ui import Modal, TextInput
from discord import Interaction, Embed, TextStyle
import logging
import time
from typing import TYPE_CHECKING

from .config import INTRO_COLOR, EXCHANGE_COLOR

if TYPE_CHECKING:
    from .views import ExchangeRequestView

logger = logging.getLogger(__name__)


class IntroOnlyModal(Modal, title="Introduce Yourself"):
    """Modal for simple introduction without exchange partner details."""

    about_me = TextInput(
        label="About Me",
        placeholder="Tell others a bit about yourself...",
        required=True,
        max_length=500,
        style=TextStyle.paragraph
    )

    interests = TextInput(
        label="Your Interests (Optional)",
        placeholder="e.g., Watching YouTube, sports, music, cooking, gaming...",
        required=False,
        max_length=500,
        style=TextStyle.paragraph
    )

    def __init__(self, introductions_channel_id: int):
        super().__init__()
        self.introductions_channel_id = introductions_channel_id

    async def on_submit(self, interaction: Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            # Get the introductions channel
            channel = interaction.client.get_channel(self.introductions_channel_id)
            if not channel:
                channel = await interaction.client.fetch_channel(self.introductions_channel_id)

            if not channel:
                await interaction.followup.send(
                    "Could not find the introductions channel. Please contact an admin.",
                    ephemeral=True
                )
                return

            # Build the intro embed
            embed = self._build_intro_embed(interaction.user)

            # Post to introductions channel
            await channel.send(embed=embed)

            # Confirm to user
            success_embed = Embed(
                title="Introduction Posted!",
                description=(
                    f"Your introduction has been posted to {channel.mention}.\n\n"
                    "Welcome to the community!"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

            logger.info(f"Introduction posted by {interaction.user} ({interaction.user.id})")

        except Exception as e:
            logger.error(f"Error posting introduction: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred while posting your introduction: {str(e)}",
                ephemeral=True
            )

    def _build_intro_embed(self, user: discord.User | discord.Member) -> Embed:
        """Build the formatted embed for intro-only posts."""
        embed = Embed(
            title="New Member Introduction",
            description=f"**{user.mention}** has joined the community!",
            color=INTRO_COLOR
        )

        # About me
        embed.add_field(
            name="About Me",
            value=self.about_me.value.strip(),
            inline=False
        )

        # Interests (if provided)
        if self.interests.value and self.interests.value.strip():
            interests_formatted = self._format_list(self.interests.value)
            embed.add_field(name="My Interests", value=interests_formatted, inline=False)

        # User avatar as thumbnail
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)

        return embed

    def _format_list(self, text: str) -> str:
        """Format text as a bulleted list if it contains commas or newlines."""
        if '\n' in text:
            items = [item.strip() for item in text.split('\n') if item.strip()]
        elif ',' in text:
            items = [item.strip() for item in text.split(',') if item.strip()]
        else:
            return text.strip()

        if len(items) <= 1:
            return text.strip()

        return '\n'.join(f"• {item}" for item in items)


class ExchangeDetailsModal(Modal, title="Exchange Partner Details"):
    """Modal for collecting free-text details about the exchange request."""

    about_me = TextInput(
        label="About Me",
        placeholder="Tell others a bit about yourself...",
        required=True,
        max_length=500,
        style=TextStyle.paragraph
    )

    activities = TextInput(
        label="Activities You'd Like To Do (Optional)",
        placeholder="e.g., Watch shows together, voice calls, text chat, play games...",
        required=False,
        max_length=500,
        style=TextStyle.paragraph
    )

    additional_info = TextInput(
        label="Additional Info (Optional)",
        placeholder="Age/age range, availability, dialect preference, etc.",
        required=False,
        max_length=500,
        style=TextStyle.paragraph
    )

    def __init__(self, parent_view: ExchangeRequestView, introductions_channel_id: int):
        super().__init__()
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id

    async def on_submit(self, interaction: Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            # Get the introductions channel
            channel = interaction.client.get_channel(self.introductions_channel_id)
            if not channel:
                channel = await interaction.client.fetch_channel(self.introductions_channel_id)

            if not channel:
                await interaction.followup.send(
                    "Could not find the introductions channel. Please contact an admin.",
                    ephemeral=True
                )
                return

            # Build the exchange request embed
            embed = self._build_request_embed(interaction.user)

            # Post to introductions channel
            await channel.send(embed=embed)

            # Confirm to user
            success_embed = Embed(
                title="Introduction Posted!",
                description=(
                    f"Your introduction has been posted to {channel.mention}.\n\n"
                    "Good luck finding a partner!"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

            logger.info(f"Exchange partner introduction posted by {interaction.user} ({interaction.user.id})")

        except Exception as e:
            logger.error(f"Error posting introduction: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred while posting your introduction: {str(e)}",
                ephemeral=True
            )

    def _format_timezone_with_timestamp(self, timezone: str) -> str:
        """Format timezone with Discord timestamp showing current local time."""
        current_unix = int(time.time())
        return f"{timezone} — <t:{current_unix}:t>"

    def _format_blockquote(self, text: str) -> str:
        """Format text as a Discord blockquote."""
        lines = text.strip().split('\n')
        return '\n'.join(f"> {line}" for line in lines)

    def _build_request_embed(self, user: discord.User | discord.Member) -> Embed:
        """Build the formatted embed for exchange partner requests."""
        pv = self.parent_view

        # Get display name
        display_name = user.display_name if hasattr(user, 'display_name') else user.name

        # Build description with About Me in blockquote
        about_me_text = self._format_blockquote(self.about_me.value.strip())
        description = f"{user.mention}'s seeking an exchange partner!\n\n**About Me**\n{about_me_text}"

        embed = Embed(
            description=description,
            color=EXCHANGE_COLOR
        )

        # Set author with user's name and avatar
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        embed.set_author(name=display_name, icon_url=avatar_url)

        # What I Offer - 3 columns
        embed.add_field(name="Language", value=pv.language_offering_display, inline=True)
        embed.add_field(name="Level", value=pv.offering_level_display, inline=True)
        timezone_formatted = self._format_timezone_with_timestamp(pv.timezone)
        embed.add_field(name="Timezone", value=timezone_formatted, inline=True)

        # "What I want" section header
        embed.add_field(
            name="⭐ What I want",
            value="-# What I'm looking for in a language partner and how we can practice together.",
            inline=False
        )

        # What I'm Looking For - 3 columns
        embed.add_field(name="Language", value=pv.language_seeking_display, inline=True)
        embed.add_field(name="Level", value=pv.seeking_level_display, inline=True)
        country_value = pv.country_display if pv.country_display and pv.country != "no_preference" else "No preference"
        embed.add_field(name="Country", value=country_value, inline=True)

        # Activities (if provided) - in blockquote
        if self.activities.value and self.activities.value.strip():
            activities_formatted = self._format_blockquote(self.activities.value.strip())
            embed.add_field(name="Activities", value=activities_formatted, inline=False)

        # Additional info (if provided) - in blockquote
        if self.additional_info.value and self.additional_info.value.strip():
            additional_formatted = self._format_blockquote(self.additional_info.value.strip())
            embed.add_field(
                name="Additional Information",
                value=additional_formatted,
                inline=False
            )

        # Footer with contact preference
        if pv.prefer_dm:
            footer_text = "Please send me DM if you want to be my language partner!"
        else:
            footer_text = "Please tag me in the server if you want to be my language partner!"
        embed.set_footer(text=footer_text)

        return embed
