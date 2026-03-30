"""Modals for the Introduce cog — free-text input forms with v2 components."""
import logging
from typing import TYPE_CHECKING

import discord
from discord import Embed, Interaction, RadioGroupOption, TextStyle
from discord.ui import Label, Modal, RadioGroup, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import EXCHANGE_COLOR, INTRO_COLOR, LANGUAGES, PROFICIENCY_LEVELS

if TYPE_CHECKING:
    from .views import ExchangePrefsView

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


def _lookup_display(options: list[tuple[str, str]], value: str) -> str:
    """Return the display label for a value from a (label, value) option list."""
    return next((label for label, v in options if v == value), value)


def _avatar_url(user: discord.User | discord.Member) -> str:
    """Return the user's avatar URL, falling back to the default avatar."""
    return user.avatar.url if user.avatar else user.default_avatar.url


async def _post_introduction(
    interaction: Interaction,
    embed: Embed,
    channel_id: int,
    success_message: str,
) -> None:
    """Shared logic: fetch channel, post embed, record to DB, confirm to user."""
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

    # Record introduction in DB for cooldown tracking / stats
    await interaction.client.db.record_introduction(interaction.user.id)

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

        embed.set_thumbnail(url=_avatar_url(interaction.user))

        await _post_introduction(interaction, embed, self.introductions_channel_id, "Welcome to the community!")

    async def on_error(self, interaction: Interaction, error: Exception):
        logger.exception("IntroOnlyModal error for user %s", interaction.user.id)
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=red_embed("Something went wrong. Please try again later."), ephemeral=True)
        else:
            await interaction.followup.send(embed=red_embed("Something went wrong. Please try again later."), ephemeral=True)


def _radio_options(options: list[tuple[str, str]]) -> list[RadioGroupOption]:
    """Convert (label, value) tuples to RadioGroupOption list."""
    return [RadioGroupOption(label=lbl, value=v) for lbl, v in options]


class ExchangeDetailsModal(Modal, title="Exchange Partner Details"):
    """Modal with RadioGroups for language/level + TextInput for about me."""

    lang_offer = Label(
        text="Language you offer",
        component=RadioGroup(options=_radio_options(LANGUAGES)),
    )
    offer_level = Label(
        text="Your level",
        component=RadioGroup(options=_radio_options(PROFICIENCY_LEVELS)),
    )
    lang_seek = Label(
        text="Language you're looking for",
        component=RadioGroup(options=_radio_options(LANGUAGES)),
    )
    seek_level = Label(
        text="Partner's minimum level",
        component=RadioGroup(options=_radio_options(PROFICIENCY_LEVELS)),
    )
    about_me = Label(
        text="About Me",
        component=TextInput(
            placeholder="Tell others about yourself, activities, additional info...",
            required=True,
            max_length=1000,
            style=TextStyle.paragraph,
        ),
    )

    def __init__(self, parent_view: "ExchangePrefsView", introductions_channel_id: int):
        super().__init__()
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id

    async def on_submit(self, interaction: Interaction):
        embed = self._build_request_embed(interaction.user)
        await _post_introduction(interaction, embed, self.introductions_channel_id, "Good luck finding a partner!")

    async def on_error(self, interaction: Interaction, error: Exception):
        logger.exception("ExchangeDetailsModal error for user %s", interaction.user.id)
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=red_embed("Something went wrong. Please try again later."), ephemeral=True)
        else:
            await interaction.followup.send(embed=red_embed("Something went wrong. Please try again later."), ephemeral=True)

    def _build_request_embed(self, user: discord.User | discord.Member) -> Embed:
        """Build the formatted embed for exchange partner requests."""
        pv = self.parent_view
        about_text = _format_blockquote(self.about_me.component.value.strip())

        lang_offer_val = self.lang_offer.component.value
        offer_level_val = self.offer_level.component.value
        lang_seek_val = self.lang_seek.component.value
        seek_level_val = self.seek_level.component.value

        embed = Embed(
            description=f"{user.mention}'s seeking an exchange partner!\n\n**About Me**\n{about_text}",
            color=EXCHANGE_COLOR,
        )

        embed.set_author(name=user.display_name, icon_url=_avatar_url(user))

        # What I Offer
        embed.add_field(name="Language", value=_lookup_display(LANGUAGES, lang_offer_val), inline=True)
        embed.add_field(name="Level", value=_lookup_display(PROFICIENCY_LEVELS, offer_level_val), inline=True)
        embed.add_field(name="Timezone", value=pv.timezone or "Not specified", inline=True)

        # What I Want
        embed.add_field(
            name="⭐ What I want",
            value="-# What I'm looking for in a language partner and how we can practice together.",
            inline=False,
        )
        embed.add_field(name="Language", value=_lookup_display(LANGUAGES, lang_seek_val), inline=True)
        embed.add_field(name="Level", value=_lookup_display(PROFICIENCY_LEVELS, seek_level_val), inline=True)
        country_value = pv.country_display if pv.country_display and pv.country != "no_preference" else "No preference"
        embed.add_field(name="Country", value=country_value, inline=True)

        footer = "Please send me DM if you want to be my language partner!" if pv.prefer_dm else "Please tag me in the server if you want to be my language partner!"
        embed.set_footer(text=footer)

        return embed
