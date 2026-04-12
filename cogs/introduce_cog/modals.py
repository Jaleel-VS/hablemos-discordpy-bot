"""Modals for the Introduce cog."""
import contextlib
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

    about_me = TextInput(label=".", required=True, max_length=500, style=TextStyle.paragraph)
    what_i_want = TextInput(label=".", required=True, max_length=500, style=TextStyle.paragraph)
    other_language = TextInput(label=".", required=False, max_length=100, style=TextStyle.short)

    def __init__(self, parent_view, introductions_channel_id: int, lang: str = "en"):
        super().__init__(title=t("modal_title_exchange", lang))
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id
        self.lang = lang

        self.about_me.label = t("label_about_me", lang)
        self.about_me.placeholder = t("placeholder_about", lang)
        self.what_i_want.label = t("label_what_i_want", lang)
        self.what_i_want.placeholder = t("placeholder_what_i_want", lang)
        self.other_language.label = t("label_other_lang", lang)
        self.other_language.placeholder = t("placeholder_other_lang", lang)

    async def on_submit(self, interaction: Interaction):
        about_text = self.about_me.value.strip()
        want_text = self.what_i_want.value.strip()
        other_lang = (self.other_language.value or "").strip()

        if contains_url(about_text) or contains_url(want_text) or contains_url(other_lang):
            await interaction.response.send_message(
                embed=red_embed(t("error_no_links", self.lang)), ephemeral=True,
            )
            return

        if self.parent_view.offer_lang == "other" and not other_lang:
            await interaction.response.send_message(
                embed=red_embed(t("error_other_lang_required", self.lang)), ephemeral=True,
            )
            return

        pv = self.parent_view
        data = _build_exchange_data(
            user=interaction.user,
            about_text=about_text,
            want_text=want_text,
            other_lang=other_lang,
            offer_lang=pv.offer_lang,
            seek_lang=pv.seek_lang,
            seek_level=pv.seek_level,
            region=pv.region,
            prefer_dm=pv.prefer_dm,
            lang=self.lang,
        )

        await _post_exchange(interaction, data, self.introductions_channel_id, self.lang)

    async def on_error(self, interaction: Interaction, error: Exception):
        logger.exception("ExchangeDetailsModal error for user %s", interaction.user.id)
        msg = red_embed(t("error_generic", self.lang))
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=msg, ephemeral=True)
        else:
            await interaction.followup.send(embed=msg, ephemeral=True)


# ── Layout builder ──


def _build_exchange_data(
    *,
    user: discord.User | discord.Member,
    about_text: str,
    want_text: str,
    other_lang: str,
    offer_lang: str,
    seek_lang: str,
    seek_level: str,
    region: str,
    prefer_dm: bool,
    lang: str,
) -> dict:
    """Build a serializable dict of exchange post data."""
    return {
        "user_id": user.id,
        "about_text": about_text,
        "want_text": want_text,
        "other_lang": other_lang,
        "offer_lang": offer_lang,
        "seek_lang": seek_lang,
        "seek_level": seek_level,
        "region": region,
        "prefer_dm": prefer_dm,
        "lang": lang,
    }


def _build_exchange_layout(
    data: dict,
    user: discord.User | discord.Member,
) -> discord.ui.LayoutView:
    """Build a LayoutView from exchange post data."""
    from .config import (
        OFFER_LANGUAGES,
        PROFICIENCY_LEVELS,
        REGIONS,
        SEEK_LANGUAGES,
    )

    lang = data["lang"]
    color = embed_color_for_member(user) if isinstance(user, Member) else COLOR_ENGLISH_NATIVE

    # Offer display
    offer_display = lookup_display(OFFER_LANGUAGES, data["offer_lang"])
    if data["offer_lang"] == "other" and data["other_lang"]:
        offer_display = data["other_lang"]
    elif data["other_lang"]:
        offer_display += f" + {data['other_lang']}"

    seek_display = lookup_display(SEEK_LANGUAGES, data["seek_lang"])
    level_display = lookup_display(PROFICIENCY_LEVELS, data["seek_level"])
    region_display = lookup_display(REGIONS, data["region"])

    footer_key = "embed_footer_dm" if data["prefer_dm"] else "embed_footer_tag"

    ui = discord.ui

    header = ui.Section(
        ui.TextDisplay(
            f"**{user.display_name}**\n"
            f"{t('embed_seeking', lang, mention=user.mention)}"
        ),
        accessory=ui.Thumbnail(avatar_url(user)),
    )

    about = ui.TextDisplay(f"**{t('label_about_me', lang)}**\n> {data['about_text'].replace(chr(10), chr(10) + '> ')}")

    want = ui.TextDisplay(f"**⭐ {t('label_what_i_want', lang)}**\n> {data['want_text'].replace(chr(10), chr(10) + '> ')}")

    offer_info = ui.TextDisplay(
        f"**{t('embed_i_speak', lang)}:** {offer_display}\n"
        f"**{t('embed_region', lang)}:** {region_display}"
    )

    seek_info = ui.TextDisplay(
        f"**{t('embed_looking_for', lang)}:** {seek_display} {t('embed_partner_suffix', lang)}\n"
        f"**{t('embed_my_level', lang)}:** {level_display}"
    )

    footer = ui.TextDisplay(f"-# {t(footer_key, lang)}")

    view = ui.LayoutView()
    view.add_item(ui.Container(
        header,
        about,
        want,
        ui.Separator(visible=True),
        offer_info,
        seek_info,
        ui.Separator(visible=True),
        footer,
        accent_colour=color,
    ))
    return view


def _build_dm_copy_embed(data: dict) -> Embed:
    """Build a simple embed copy for DM."""
    from .config import (
        OFFER_LANGUAGES,
        PROFICIENCY_LEVELS,
        REGIONS,
        SEEK_LANGUAGES,
    )

    lang = data["lang"]
    offer_display = lookup_display(OFFER_LANGUAGES, data["offer_lang"])
    if data["offer_lang"] == "other" and data["other_lang"]:
        offer_display = data["other_lang"]
    elif data["other_lang"]:
        offer_display += f" + {data['other_lang']}"

    embed = Embed(
        title="Your Exchange Partner Post",
        description=f"Here's a copy of what was posted. Manage it with `/exchange`.\n\n**About Me**\n> {data['about_text'][:400]}\n\n**⭐ What I'm looking for**\n> {data['want_text'][:400]}",
    )
    embed.add_field(name=t("embed_i_speak", lang), value=offer_display, inline=True)
    embed.add_field(name=t("embed_region", lang), value=lookup_display(REGIONS, data["region"]), inline=True)
    embed.add_field(
        name=t("embed_looking_for", lang),
        value=f"{lookup_display(SEEK_LANGUAGES, data['seek_lang'])} — {lookup_display(PROFICIENCY_LEVELS, data['seek_level'])}",
        inline=False,
    )
    return embed


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


async def _post_exchange(interaction: Interaction, data: dict, channel_id: int, lang: str) -> None:
    """Post an exchange partner LayoutView and track it in the DB."""
    await interaction.response.defer(ephemeral=True)

    # Check for existing post
    existing = await interaction.client.db.get_exchange_post(interaction.user.id)
    if existing:
        await interaction.followup.send(
            embed=red_embed(t("error_already_posted", lang)), ephemeral=True,
        )
        await _audit_log(interaction.client, interaction.user, "Exchange blocked (duplicate)")
        return

    channel = await _resolve_channel(interaction, channel_id)
    if not channel:
        return

    view = _build_exchange_layout(data, interaction.user)

    try:
        msg = await channel.send(view=view)
    except discord.Forbidden:
        logger.error("Missing permissions to post in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed(t("error_generic", lang)), ephemeral=True)
        return
    except discord.HTTPException:
        logger.exception("Failed to post exchange request in channel %s", channel_id)
        await interaction.followup.send(embed=red_embed(t("error_generic", lang)), ephemeral=True)
        return

    await interaction.client.db.record_introduction(interaction.user.id)
    await interaction.client.db.save_exchange_post(interaction.user.id, msg.id, channel_id, post_data=data)

    await interaction.followup.send(
        embed=green_embed(t("success_exchange", lang, channel=channel.mention)), ephemeral=True,
    )
    await _audit_log(interaction.client, interaction.user, "Exchange posted")

    # DM the user a copy
    try:
        await interaction.user.send(embed=_build_dm_copy_embed(data))
    except discord.HTTPException:
        logger.debug("Could not DM user %s a copy of their exchange post", interaction.user.id)
        with contextlib.suppress(discord.HTTPException):
            await interaction.followup.send(
                embed=red_embed(t("dm_copy_failed", lang)), ephemeral=True,
            )


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
