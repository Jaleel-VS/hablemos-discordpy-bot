"""Modals for the Introduce cog (introductions only).

Language-exchange posting lives in ``langex_cog``.
"""
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


def avatar_url(user: discord.User | discord.Member) -> str:
    """Return the user's display avatar URL (always resolves)."""
    return user.display_avatar.url


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
    """Modal for a simple member introduction."""

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


# ── Post helpers ──


async def _audit_log(client, user: discord.User | discord.Member, action: str) -> None:
    """Send a minimal audit entry to the audit channel."""
    from .config import AUDIT_CHANNEL_ID

    channel = client.get_channel(AUDIT_CHANNEL_ID)
    if not channel:
        return
    try:
        await channel.send(f"📋 **{action}** — {user} (`{user.id}`)")
    except discord.HTTPException:
        logger.debug("Failed to send audit log for %s", action)


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
    await _audit_log(interaction.client, interaction.user, "Introduction posted")


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
