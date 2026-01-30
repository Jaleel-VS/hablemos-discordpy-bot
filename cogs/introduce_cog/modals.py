from __future__ import annotations

import discord
from discord.ui import Modal, TextInput
from discord import Interaction, Embed, TextStyle
import logging
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
        label="About Me (Optional)",
        placeholder="Tell others a bit about yourself...",
        required=False,
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

    def _build_request_embed(self, user: discord.User | discord.Member) -> Embed:
        """Build the formatted embed for exchange partner requests."""
        pv = self.parent_view

        # Build description with contact preference and exchange badge
        if pv.prefer_dm:
            contact_pref = "📩 *Please send me a DM*"
        else:
            contact_pref = "💬 *Please tag me in the server*"

        embed = Embed(
            title="New Member Introduction",
            description=f"**{user.mention}** 🔄 **Seeking Exchange Partner**\n\n{contact_pref}",
            color=EXCHANGE_COLOR
        )

        # About me (if provided) - at the top
        if self.about_me.value and self.about_me.value.strip():
            embed.add_field(
                name="About Me",
                value=self.about_me.value.strip(),
                inline=False
            )

        # What I Offer - 3 columns
        embed.add_field(name="Offering Language", value=pv.language_offering_display, inline=True)
        embed.add_field(name="My Level", value=pv.offering_level_display, inline=True)
        embed.add_field(name="Timezone", value=pv.timezone, inline=True)

        # What I'm Looking For - 3 columns
        embed.add_field(name="Seeking Language", value=pv.language_seeking_display, inline=True)
        embed.add_field(name="Partner Level", value=pv.seeking_level_display, inline=True)
        embed.add_field(name="Country", value=pv.country_display or "No Preference", inline=True)

        # Interests (if provided)
        if self.interests.value and self.interests.value.strip():
            interests_formatted = self._format_list(self.interests.value)
            embed.add_field(name="My Interests", value=interests_formatted, inline=False)

        # Activities (if provided)
        if self.activities.value and self.activities.value.strip():
            activities_formatted = self._format_list(self.activities.value)
            embed.add_field(name="Activities I'd Like To Do", value=activities_formatted, inline=False)

        # Additional info (if provided)
        if self.additional_info.value and self.additional_info.value.strip():
            embed.add_field(
                name="Additional Information",
                value=self.additional_info.value.strip(),
                inline=False
            )

        # User avatar as thumbnail
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)

        return embed

    def _format_list(self, text: str) -> str:
        """Format text as a bulleted list if it contains commas or newlines."""
        # Split by newlines or commas
        if '\n' in text:
            items = [item.strip() for item in text.split('\n') if item.strip()]
        elif ',' in text:
            items = [item.strip() for item in text.split(',') if item.strip()]
        else:
            return text.strip()

        if len(items) <= 1:
            return text.strip()

        return '\n'.join(f"• {item}" for item in items)
