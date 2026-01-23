from __future__ import annotations

import discord
from discord.ui import Modal, TextInput
from discord import Interaction, Embed, TextStyle
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .views import ExchangeRequestView

logger = logging.getLogger(__name__)


class ExchangeDetailsModal(Modal, title="Exchange Partner Details"):
    """Modal for collecting free-text details about the exchange request."""

    interests = TextInput(
        label="Your Interests",
        placeholder="e.g., Watching YouTube, sports, music, cooking, gaming...",
        required=True,
        max_length=500,
        style=TextStyle.paragraph
    )

    activities = TextInput(
        label="Activities You'd Like To Do",
        placeholder="e.g., Watch shows together, voice calls, text chat, play games...",
        required=True,
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

    def __init__(self, parent_view: ExchangeRequestView, results_channel_id: int):
        super().__init__()
        self.parent_view = parent_view
        self.results_channel_id = results_channel_id

    async def on_submit(self, interaction: Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            # Get the results channel
            results_channel = interaction.client.get_channel(self.results_channel_id)
            if not results_channel:
                results_channel = await interaction.client.fetch_channel(self.results_channel_id)

            if not results_channel:
                await interaction.followup.send(
                    "Could not find the results channel. Please contact an admin.",
                    ephemeral=True
                )
                return

            # Build the exchange request embed
            embed = self._build_request_embed(interaction.user)

            # Post to results channel
            await results_channel.send(embed=embed)

            # Confirm to user
            success_embed = Embed(
                title="Request Submitted!",
                description=(
                    f"Your exchange partner request has been posted to {results_channel.mention}.\n\n"
                    "Good luck finding a partner!"
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

            logger.info(f"Exchange request submitted by {interaction.user} ({interaction.user.id})")

        except Exception as e:
            logger.error(f"Error submitting exchange request: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred while submitting your request: {str(e)}",
                ephemeral=True
            )

    def _build_request_embed(self, user: discord.User | discord.Member) -> Embed:
        """Build the formatted embed for the results channel."""
        pv = self.parent_view

        # Build description
        dm_indicator = "📩 *Prefers DM contact*\n\n" if pv.prefer_dm else ""

        embed = Embed(
            title="Language Exchange Partner Request",
            description=f"{dm_indicator}**{user.mention}** is looking for a language exchange partner!",
            color=discord.Color.blue()
        )

        # What I Offer section
        offer_text = (
            f"**Language:** {pv.language_offering_display}\n"
            f"**Level:** {pv.offering_level_display}\n"
            f"**Timezone:** {pv.timezone_display}"
        )
        embed.add_field(name="What I Offer", value=offer_text, inline=False)

        # What I'm Looking For section
        seeking_text = (
            f"**Language:** {pv.language_seeking_display}\n"
            f"**Minimum Level:** {pv.seeking_level_display}"
        )
        embed.add_field(name="What I'm Looking For", value=seeking_text, inline=False)

        # Interests
        interests_formatted = self._format_list(self.interests.value)
        embed.add_field(name="My Interests", value=interests_formatted, inline=False)

        # Activities
        activities_formatted = self._format_list(self.activities.value)
        embed.add_field(name="Activities I'd Like To Do", value=activities_formatted, inline=False)

        # Additional info (if provided)
        if self.additional_info.value and self.additional_info.value.strip():
            embed.add_field(
                name="Additional Information",
                value=self.additional_info.value.strip(),
                inline=False
            )

        # Footer with contact instruction
        contact_method = "send me a DM" if pv.prefer_dm else "reach out to me"
        embed.set_footer(
            text=f"If you're interested in being my exchange partner, please {contact_method}!"
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
