"""Persistent UI for the Almighty cog (working title).

``TriggerView`` is a timeout-less view with two buttons posted in the
trigger channel:

- **Submit** opens ``SubmissionModal`` (free-text subject + details).
- **Categorize** opens ``CategoryModal`` (a single-choice radio group
  plus an optional note).

Either modal relays an embed to the feed channel. Write in one channel,
read in another.
"""
from __future__ import annotations

import logging

import discord
from discord import Color, Embed, Interaction, RadioGroupOption, TextStyle
from discord.ext import commands
from discord.ui import Label, Modal, RadioGroup, TextInput

from cogs.utils.embeds import red_embed

from .config import CATEGORIES, FEED_CHANNEL_ID

logger = logging.getLogger(__name__)


async def _relay_to_feed(bot: commands.Bot, interaction: Interaction, embed: Embed) -> None:
    """Post `embed` to the feed channel, reporting status to the user.

    Acknowledges the interaction *first* (ephemeral "submitting") so the
    modal always closes within Discord's 3s window, then edits that
    message to the final result. Safe against a slow or failing feed send.
    """
    await interaction.response.send_message(
        embed=Embed(description="⏳ Submitting…", color=Color.blurple()),
        ephemeral=True,
    )

    feed = bot.get_channel(FEED_CHANNEL_ID)
    if not isinstance(feed, discord.abc.Messageable):
        logger.error("Almighty feed channel %s unavailable", FEED_CHANNEL_ID)
        await interaction.edit_original_response(
            embed=red_embed("The feed channel is unavailable right now. Try again later."),
        )
        return

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


def _attribute(embed: Embed, user: discord.User | discord.Member) -> Embed:
    """Stamp an embed with the submitter's identity."""
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.set_footer(text=f"Submitted by {user} • {user.id}")
    return embed


class _RelayModal(Modal):
    """Base modal: holds the bot and a uniform error backstop."""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        # Any unhandled error in on_submit lands here. Make sure the
        # interaction is acknowledged so the user never sees a silent
        # "interaction failed" with the modal stuck open.
        logger.error("Almighty modal error: %s", error, exc_info=True)
        message = red_embed("Something went wrong. Please try again later.")
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=message)
            else:
                await interaction.response.send_message(embed=message, ephemeral=True)
        except discord.HTTPException:
            pass


class SubmissionModal(_RelayModal, title="New submission"):
    """Free-text form: a subject and a details body."""

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

    async def on_submit(self, interaction: Interaction) -> None:
        embed = _attribute(
            Embed(
                title=str(self.subject.value),
                description=str(self.details.value),
                color=Color.blurple(),
                timestamp=interaction.created_at,
            ),
            interaction.user,
        )
        await _relay_to_feed(self.bot, interaction, embed)


class CategoryModal(_RelayModal, title="Categorize"):
    """Single-choice radio group plus an optional note."""

    category: Label = Label(
        text="Category",
        description="Pick one",
        component=RadioGroup(
            custom_id="almighty:category_choice",
            required=True,
            options=[
                RadioGroupOption(label=label, value=label, description=desc)
                for label, desc in CATEGORIES
            ],
        ),
    )
    note: Label = Label(
        text="Note",
        description="Optional",
        component=TextInput(
            style=TextStyle.paragraph,
            placeholder="Add context (optional)…",
            max_length=1000,
            required=False,
        ),
    )

    async def on_submit(self, interaction: Interaction) -> None:
        radio: RadioGroup = self.category.component  # type: ignore[assignment]
        note: TextInput = self.note.component  # type: ignore[assignment]
        choice = radio.value or "—"
        body = str(note.value) if note.value else "_(no note)_"
        embed = _attribute(
            Embed(
                title=f"📂 {choice}",
                description=body,
                color=Color.blurple(),
                timestamp=interaction.created_at,
            ),
            interaction.user,
        )
        await _relay_to_feed(self.bot, interaction, embed)


class TriggerView(discord.ui.View):
    """Persistent (timeout-less) view with the two form-opening buttons."""

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

    @discord.ui.button(
        label="Categorize",
        style=discord.ButtonStyle.secondary,
        custom_id="almighty:categorize",
        emoji="📂",
    )
    async def categorize_button(self, interaction: Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(CategoryModal(self.bot))
