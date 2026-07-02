"""Persistent and ephemeral views for the Language Exchange cog.

- ``LangExPanelView``: the persistent hub (Post / Find / Delete buttons).
- ``PrefsView``: ephemeral select-driven step before the details modal.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import ButtonStyle, Color, Embed, Interaction, SelectOption
from discord.ui import Button, Select, View, button

from cogs.utils.embeds import green_embed, red_embed

from .config import (
    MATCH_RESULT_LIMIT,
    OFFER_LANGUAGES,
    PROFICIENCY_LEVELS,
    REGIONS,
    SEEK_LANGUAGES,
    detect_ui_lang,
)
from .embeds import build_matches_embed
from .i18n import t
from .matching import rank_matches
from .modals import DetailsModal

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def _ui_lang(interaction: Interaction) -> str:
    user = interaction.user
    return detect_ui_lang(user) if isinstance(user, discord.Member) else "en"


class PrefsView(View):
    """Ephemeral selects: offer / seek / level / region / DM, then modal."""

    def __init__(self, bot: Hablemos, lang: str = "en", timeout: float = 300):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.lang = lang
        self.offer_lang: str | None = None
        self.seek_lang: str | None = None
        self.seek_level: str | None = None
        self.region: str | None = None
        self.prefer_dm: bool | None = None
        self._build()

    def _build(self) -> None:
        self.add_item(self._select("select_offer", OFFER_LANGUAGES, 0, "offer_lang"))
        self.add_item(self._select("select_seek", SEEK_LANGUAGES, 1, "seek_lang"))
        self.add_item(self._select("select_level", PROFICIENCY_LEVELS, 2, "seek_level"))
        self.add_item(self._select("select_region", REGIONS, 3, "region"))
        self.continue_button.label = t("btn_next", self.lang)

    def _select(self, placeholder_key: str, options: list[tuple[str, str]], row: int, attr: str) -> Select:
        select = Select(
            placeholder=t(placeholder_key, self.lang),
            options=[SelectOption(label=lbl, value=v) for lbl, v in options],
            row=row,
        )

        async def cb(interaction: Interaction):
            data = interaction.data
            values = data.get("values") if data else None
            if values:
                setattr(self, attr, values[0])
            await interaction.response.defer()

        select.callback = cb
        return select

    @button(label="Next →", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, _btn: Button):
        missing = []
        if not self.offer_lang:
            missing.append(t("field_offer", self.lang))
        if not self.seek_lang:
            missing.append(t("field_seek", self.lang))
        if not self.seek_level:
            missing.append(t("field_level", self.lang))
        if not self.region:
            missing.append(t("field_region", self.lang))
        if missing:
            await interaction.response.send_message(
                embed=red_embed(t("missing_fields", self.lang, fields=", ".join(missing))),
                ephemeral=True,
            )
            return
        if self.offer_lang == self.seek_lang:
            await interaction.response.send_message(
                embed=red_embed(t("error_same_language", self.lang)), ephemeral=True,
            )
            return

        prefs = {
            "offer_lang": self.offer_lang,
            "seek_lang": self.seek_lang,
            "seek_level": self.seek_level,
            "region": self.region,
            "prefer_dm": self.prefer_dm if self.prefer_dm is not None else True,
        }
        await interaction.response.send_modal(DetailsModal(self.bot, prefs, self.lang))

    async def on_timeout(self) -> None:
        logger.debug("Langex PrefsView timed out")


class LangExPanelView(View):
    """Persistent hub: Post / update, Find a partner, Delete my profile."""

    def __init__(self, bot: Hablemos):
        super().__init__(timeout=None)
        self.bot = bot

    @button(
        label="Post / update profile",
        style=ButtonStyle.success,
        custom_id="langex:post",
        emoji="📝",
    )
    async def post_button(self, interaction: Interaction, _btn: Button):
        lang = _ui_lang(interaction)
        embed = Embed(
            title=t("prefs_title", lang),
            description=t("prefs_body", lang),
            color=Color.teal(),
        )
        await interaction.response.send_message(
            embed=embed, view=PrefsView(self.bot, lang), ephemeral=True,
        )

    @button(
        label="Find a partner",
        style=ButtonStyle.primary,
        custom_id="langex:find",
        emoji="🔎",
    )
    async def find_button(self, interaction: Interaction, _btn: Button):
        lang = _ui_lang(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)

        me = await self.bot.db.get_exchange_post(interaction.user.id)
        if not me or not me.get("post_data"):
            await interaction.followup.send(embed=red_embed(t("find_no_profile", lang)), ephemeral=True)
            return

        others = await self.bot.db.get_all_exchange_posts()
        matches = rank_matches(me, others, limit=MATCH_RESULT_LIMIT)
        if not matches:
            await interaction.followup.send(embed=red_embed(t("find_no_matches", lang)), ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        await interaction.followup.send(
            embed=build_matches_embed(matches, lang, guild_id), ephemeral=True,
        )

    @button(
        label="Delete my profile",
        style=ButtonStyle.secondary,
        custom_id="langex:delete",
        emoji="🗑️",
    )
    async def delete_button(self, interaction: Interaction, _btn: Button):
        lang = _ui_lang(interaction)
        existing = await self.bot.db.get_exchange_post(interaction.user.id)
        if not existing:
            await interaction.response.send_message(embed=red_embed(t("delete_none", lang)), ephemeral=True)
            return

        await _delete_message(self.bot, existing.get("channel_id"), existing.get("message_id"))
        await self.bot.db.delete_exchange_post(interaction.user.id)
        await interaction.response.send_message(embed=green_embed(t("delete_ok", lang)), ephemeral=True)


async def _delete_message(bot: Hablemos, channel_id: int | None, message_id: int | None) -> None:
    if not channel_id or not message_id:
        return
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        return
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass
