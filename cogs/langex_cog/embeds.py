"""Embed builders for the Language Exchange cog.

The posted profile is now a Components V2 ``LayoutView`` (see
``components.py``); this module only builds the ephemeral match-results
embed.
"""
from __future__ import annotations

from discord import Color, Embed

from .config import LANG_FLAGS, REGIONS
from .i18n import t
from .matching import Match


def _lookup(options: list[tuple[str, str]], value: str | None) -> str:
    """Return the display label for a stored value."""
    return next((label for label, v in options if v == value), value or "—")


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
