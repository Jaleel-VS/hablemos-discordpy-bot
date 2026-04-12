"""Modals for the Introduce cog."""
import logging
import re

import discord
from discord import Embed, Interaction, Member, TextStyle
from discord.ui import Modal, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import (
    COLOR_BOTH_NATIVE,
    COLOR_ENGLISH_NATIVE,
    COLOR_INTRO,
    COLOR_OTHER_NATIVE,
    COLOR_SPANISH_NATIVE,
    ENGLISH_NATIVE_ROLE_ID,
    OTHER_NATIVE_ROLE_ID,
    SPANISH_NATIVE_ROLE_ID,
)
from .i18n import t

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+|www\.\S+|\[.*?\]\(.*?\)", re.IGNORECASE)


def contains_url(text: str) -> bool:
    """Check if text contains URLs or markdown links."""
    return bool(_URL_RE.search(text))


def lookup_display(options: list[tuple[str, str]], value: str) -> str:
    """Return the display label for a value from a (label, value) option list."""
    return next((label for label, v in options if v == value), value)


def avatar_url(user: discord.User | discord.Member) -> str:
    """Return the user's avatar URL, falling back to the default avatar."""
    return user.avatar.url if user.avatar else user.default_avatar.url


def embed_color_for_member(member: Member) -> discord.Color:
    """Determine embed color based on the member's native-language roles."""
    role_ids = {r.id for r in member.roles}
    has_eng = ENGLISH_NATIVE_ROLE_ID in role_ids
    has_spa = SPANISH_NATIVE_ROLE_ID in role_ids
    has_other = OTHER_NATIVE_ROLE_ID in role_ids

    if has_eng and has_spa:
        return COLOR_BOTH_NATIVE
    if has_spa:
        return COLOR_SPANISH_NATIVE
    if has_eng:
        return COLOR_ENGLISH_NATIVE
    if has_other:
        return COLOR_OTHER_NATIVE
    return COLOR_ENGLISH_NATIVE


class IntroOnlyModal(Modal):
    """Modal for simple introduction without exchange partner details."""

    about_me = TextInput(label=".", required=True, max_length=500, style=TextStyle.paragraph)
    interests = TextInput(label=".", required=False, max_length=500, style=TextStyle.paragraph)

    def __init__(self, introductions_channel_id: int, lang: str = "en"):
        super().__init__(title=t("modal_title_intro", lang))
        self.introductions_channel_id = introductions_channel_id
        self.lang = lang

        self.about_me.label = t("label_about_me", lang)
        self.about_me.placeholder = t("placeholder_about_me", lang)
        self.interests.label = t("label_interests", lang)
        self.interests.placeholder = t("placeholder_interests", lang)

    async def on_submit(self, interaction: Interaction):
        about = self.about_me.value.strip()
        interests = (self.interests.value or "").strip()

        if contains_url(about) or contains_url(interests):
            await interaction.response.send_message(
                embed=red_embed(t("error_no_links", self.lang)), ephemeral=True,
            )
            return

        embed = Embed(
            title=t("embed_intro_title", self.lang),
            description=t("embed_intro_joined", self.lang, mention=interaction.user.mention),
            color=COLOR_INTRO,
        )
        embed.add_field(name=t("label_about_me", self.lang), value=about, inline=False)
        if interests:
            embed.add_field(name=t("label_interests", self.lang), value=interests, inline=False)
        embed.set_thumbnail(url=avatar_url(interaction.user))

        await _post_intro(interaction, embed, self.introductions_channel_id, self.lang)

    async def on_error(self, interaction: Interaction, error: Exception):
        logger.exception("IntroOnlyModal error for user %s", interaction.user.id)
        msg = red_embed(t("error_generic", self.lang))
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=msg, ephemeral=True)
        else:
            await interaction.followup.send(embed=msg, ephemeral=True)


class ExchangeDetailsModal(Modal):
    """Single modal: about me + what I'm looking for. Language/region collected in the view."""

    about_and_wants = TextInput(label=".", required=True, max_length=1000, style=TextStyle.paragraph)
    other_language = TextInput(label=".", required=False, max_length=100, style=TextStyle.short)

    def __init__(self, parent_view, introductions_channel_id: int, lang: str = "en"):
        super().__init__(title=t("modal_title_exchange", lang))
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id
        self.lang = lang

        self.about_and_wants.label = t("label_about", lang)
        self.about_and_wants.placeholder = t("placeholder_about", lang)
        self.other_language.label = t("label_other_lang", lang)
        self.other_language.placeholder = t("placeholder_other_lang", lang)

    async def on_submit(self, interaction: Interaction):
        about_text = self.about_and_wants.value.strip()
        other_lang = (self.other_language.value or "").strip()

        if contains_url(about_text) or contains_url(other_lang):
            await interaction.response.send_message(
                embed=red_embed(t("error_no_links", self.lang)), ephemeral=True,
            )
            return

        pv = self.parent_view
        embed = _build_exchange_embed(
            user=interaction.user,
            about_text=about_text,
            other_lang=other_lang,
            offer_lang=pv.offer_lang,
            seek_lang=pv.seek_lang,
            seek_level=pv.seek_level,
            region=pv.region,
            prefer_dm=pv.prefer_dm,
            lang=self.lang,
        )

        await _post_exchange(interaction, embed, self.introductions_channel_id, self.lang)

    async def on_error(self, interaction: Interaction, error: Exception):
        logger.exception("ExchangeDetailsModal error for user %s", interaction.user.id)
        msg = red_embed(t("error_generic", self.lang))
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=msg, ephemeral=True)
        else:
            await interaction.followup.send(embed=msg, ephemeral=True)


# ── Embed builders ──


def _build_exchange_embed(
    *,
    user: discord.User | discord.Member,
    about_text: str,
    other_lang: str,
    offer_lang: str,
    seek_lang: str,
    seek_level: str,
    region: str,
    prefer_dm: bool,
    lang: str,
) -> Embed:
    """Build the exchange partner embed."""
    from .config import (
        OFFER_LANGUAGES,
        PROFICIENCY_LEVELS,
        REGIONS,
        SEEK_LANGUAGES,
    )

    color = embed_color_for_member(user) if isinstance(user, Member) else COLOR_ENGLISH_NATIVE
    about_quoted = "\n".join(f"> {line}" for line in about_text.split("\n"))

    embed = Embed(
        description=t("embed_seeking", lang, mention=user.mention) + f"\n\n{about_quoted}",
        color=color,
    )
    embed.set_author(name=user.display_name, icon_url=avatar_url(user))

    # What I offer
    offer_display = lookup_display(OFFER_LANGUAGES, offer_lang)
    if offer_lang == "other" and other_lang:
        offer_display = other_lang
    elif other_lang:
        offer_display += f" + {other_lang}"
    embed.add_field(name=t("embed_i_speak", lang), value=offer_display, inline=True)
    embed.add_field(name=t("embed_region", lang), value=lookup_display(REGIONS, region), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    # What I want
    seek_display = lookup_display(SEEK_LANGUAGES, seek_lang)
    embed.add_field(
        name=t("embed_looking_for", lang),
        value=f"{seek_display} {t('embed_partner_suffix', lang)}",
        inline=True,
    )
    embed.add_field(name=t("embed_my_level", lang), value=lookup_display(PROFICIENCY_LEVELS, seek_level), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    footer_key = "embed_footer_dm" if prefer_dm else "embed_footer_tag"
    embed.set_footer(text=t(footer_key, lang))

    return embed


# ── Post helpers ──


async def _post_intro(interaction: Interaction, embed: Embed, channel_id: int, lang: str) -> None:
    """Post a simple introduction embed."""
    await interaction.response.defer(ephemeral=True)
    channel = await _resolve_channel(interaction, channel_id)
    if not channel:
        return

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        logger.error("Missing permissions to post in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed(t("error_generic", lang)), ephemeral=True)
        return
    except discord.HTTPException:
        logger.exception("Failed to post introduction in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed(t("error_generic", lang)), ephemeral=True)
        return

    await interaction.client.db.record_introduction(interaction.user.id)
    await interaction.followup.send(
        embed=green_embed(t("success_intro", lang, channel=channel.mention)), ephemeral=True,
    )


async def _post_exchange(interaction: Interaction, embed: Embed, channel_id: int, lang: str) -> None:
    """Post an exchange partner embed and track it in the DB."""
    await interaction.response.defer(ephemeral=True)
    channel = await _resolve_channel(interaction, channel_id)
    if not channel:
        return

    try:
        msg = await channel.send(embed=embed)
    except discord.Forbidden:
        logger.error("Missing permissions to post in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed(t("error_generic", lang)), ephemeral=True)
        return
    except discord.HTTPException:
        logger.exception("Failed to post exchange request in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed(t("error_generic", lang)), ephemeral=True)
        return

    await interaction.client.db.record_introduction(interaction.user.id)
    await interaction.client.db.save_exchange_post(interaction.user.id, msg.id, channel_id)

    await interaction.followup.send(
        embed=green_embed(t("success_exchange", lang, channel=channel.mention)), ephemeral=True,
    )

    # DM the user a copy of their info
    try:
        dm_embed = Embed(
            title="Your Exchange Partner Post",
            description="Here's a copy of what was posted. You can manage it with `/exchange`.",
            color=embed.color,
        )
        for field in embed.fields:
            if field.name != "\u200b":
                dm_embed.add_field(name=field.name, value=field.value, inline=field.inline)
        if embed.description:
            dm_embed.add_field(name="Full text", value=embed.description[:1024], inline=False)
        await interaction.user.send(embed=dm_embed)
    except discord.HTTPException:
        logger.debug("Could not DM user %s a copy of their exchange post", interaction.user.id)


async def _resolve_channel(interaction: Interaction, channel_id: int):
    """Get or fetch a channel, sending error on failure."""
    channel = interaction.client.get_channel(channel_id)
    if channel:
        return channel
    try:
        return await interaction.client.fetch_channel(channel_id)
    except discord.NotFound:
        logger.error("Channel %s not found", channel_id)
        await interaction.followup.send(embed=red_embed("Target channel not found."), ephemeral=True)
    except discord.HTTPException:
        logger.exception("Failed to fetch channel %s", channel_id)
        await interaction.followup.send(embed=red_embed("Could not reach the target channel."), ephemeral=True)
    return None
