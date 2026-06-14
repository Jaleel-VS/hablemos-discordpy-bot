"""Embed builders for the Language Exchange cog."""
from __future__ import annotations

import discord
from discord import Color, Embed, Member

from .config import (
    COLOR_BOTH_NATIVE,
    COLOR_ENGLISH_NATIVE,
    COLOR_OTHER_NATIVE,
    COLOR_SPANISH_NATIVE,
    ENGLISH_NATIVE_ROLE_ID,
    LANG_FLAGS,
    OFFER_LANGUAGES,
    REGIONS,
    SEEK_LANGUAGES,
    SPANISH_NATIVE_ROLE_ID,
)
from .i18n import t
from .matching import Match


def _lookup(options: list[tuple[str, str]], value: str | None) -> str:
    """Return the display label for a stored value."""
    return next((label for label, v in options if v == value), value or "—")


def embed_color_for_member(member: Member) -> Color:
    """Color the profile embed by the member's native-language role combo."""
    role_ids = {r.id for r in member.roles}
    has_en = ENGLISH_NATIVE_ROLE_ID in role_ids
    has_es = SPANISH_NATIVE_ROLE_ID in role_ids
    if has_en and has_es:
        return COLOR_BOTH_NATIVE
    if has_es:
        return COLOR_SPANISH_NATIVE
    if has_en:
        return COLOR_ENGLISH_NATIVE
    return COLOR_OTHER_NATIVE


def build_profile_embed(data: dict, user: discord.User | discord.Member) -> Embed:
    """The public profile embed posted to the feed channel."""
    lang = data.get("lang", "en")
    color = embed_color_for_member(user) if isinstance(user, Member) else COLOR_ENGLISH_NATIVE

    offer = _lookup(OFFER_LANGUAGES, data.get("offer_lang"))
    if data.get("offer_lang") == "other" and data.get("other_lang"):
        offer = data["other_lang"]
    seek = _lookup(SEEK_LANGUAGES, data.get("seek_lang"))
    level = data.get("seek_level") or "—"
    region = _lookup(REGIONS, data.get("region"))

    embed = Embed(color=color)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)

    if data.get("about_text"):
        about = "\n".join(f"-# {line}" for line in str(data["about_text"]).split("\n"))
        embed.add_field(name=t("modal_about_label", lang), value=about, inline=False)

    embed.add_field(name="🗣️ Speaks", value=offer, inline=True)
    embed.add_field(name="📚 Learning", value=f"{seek} ({level})", inline=True)
    embed.add_field(name="🌍 Region", value=region, inline=True)

    if data.get("want_text"):
        want = "\n".join(f"-# {line}" for line in str(data["want_text"]).split("\n"))
        embed.add_field(name="⭐ Looking for", value=want, inline=False)

    if data.get("interests"):
        embed.add_field(name="🎯 Interests", value=str(data["interests"])[:1024], inline=False)

    contact = "📩 DM me" if data.get("prefer_dm", True) else "🔔 Tag me in the server"
    embed.set_footer(text=contact)
    return embed


def build_matches_embed(matches: list[Match], lang: str, guild_id: int) -> Embed:
    """Ephemeral embed listing ranked matches with jump links."""
    embed = Embed(
        title=t("panel_title", lang),
        description=t("find_header", lang),
        color=Color.teal(),
    )
    jump_label = t("find_jump", lang)
    lines = []
    for i, m in enumerate(matches, 1):
        offer_flag = LANG_FLAGS.get(m.offer_lang, "🌐")
        seek_flag = LANG_FLAGS.get(m.seek_lang, "🌐")
        level = f" ({m.seek_level})" if m.seek_level else ""
        region = _lookup(REGIONS, m.region) if m.region else "—"
        jump = f"https://discord.com/channels/{guild_id}/{m.channel_id}/{m.message_id}"
        lines.append(
            f"**{i}.** <@{m.user_id}> · speaks {offer_flag} ↔ learning {seek_flag}{level} "
            f"· {region} · [{jump_label}]({jump})"
        )
    embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
    return embed
