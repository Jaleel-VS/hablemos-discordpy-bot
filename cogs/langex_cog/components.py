"""Components V2 layout for a posted language-exchange profile.

A profile is a ``LayoutView`` (Container → Sections/TextDisplays) rather
than a flat embed, giving an avatar accessory and a clean card layout.
"""
from __future__ import annotations

import logging

import discord
from discord import Color, Member
from discord.ui import (
    Container,
    LayoutView,
    Section,
    Separator,
    TextDisplay,
    Thumbnail,
)

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

logger = logging.getLogger(__name__)

def _lookup(options: list[tuple[str, str]], value: str | None) -> str:
    return next((label for label, v in options if v == value), value or "—")

def _color_for_member(member: Member) -> Color:
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

def build_profile_view(data: dict, user: discord.User | discord.Member) -> LayoutView:
    """Build the Components V2 profile card for the feed channel."""
    lang = data.get("lang", "en")
    color = _color_for_member(user) if isinstance(user, Member) else COLOR_ENGLISH_NATIVE

    offer = _lookup(OFFER_LANGUAGES, data.get("offer_lang"))
    if data.get("offer_lang") == "other" and data.get("other_lang"):
        offer = data["other_lang"]
    offer_flag = LANG_FLAGS.get(data.get("offer_lang", ""), "🌐")
    seek = _lookup(SEEK_LANGUAGES, data.get("seek_lang"))
    seek_flag = LANG_FLAGS.get(data.get("seek_lang", ""), "🌐")
    level = data.get("seek_level") or "—"
    region = _lookup(REGIONS, data.get("region"))

    header = (
        f"## {user.display_name}\n"
        f"{offer_flag} **Speaks** {offer}  ·  {seek_flag} **Learning** {seek} ({level})\n"
        f"🌍 {region}"
    )

    container = Container(accent_colour=color)
    container.add_item(
        Section(
            TextDisplay(header),
            accessory=Thumbnail(user.display_avatar.url),
        )
    )
    container.add_item(Separator())

    if data.get("about_text"):
        about = "\n".join(f"-# {line}" for line in str(data["about_text"]).split("\n"))
        container.add_item(TextDisplay(f"**About**\n{about}"))
    if data.get("want_text"):
        want = "\n".join(f"-# {line}" for line in str(data["want_text"]).split("\n"))
        container.add_item(TextDisplay(f"**⭐ Looking for**\n{want}"))
    if data.get("interests"):
        container.add_item(TextDisplay(f"**🎯 Interests** {str(data['interests'])[:500]}"))

    container.add_item(Separator())
    contact_hint = t("post_contact_dm", lang) if data.get("prefer_dm", True) else t("post_contact_tag", lang)
    container.add_item(TextDisplay(f"<@{data['user_id']}> · -# {contact_hint}"))

    view = LayoutView(timeout=None)
    view.add_item(container)
    return view
