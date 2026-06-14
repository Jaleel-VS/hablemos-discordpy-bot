"""Modals for the Language Exchange cog."""
from __future__ import annotations

import logging
import re

import discord
from discord import Interaction, TextStyle
from discord.ext import commands
from discord.ui import Label, Modal, TextInput

from cogs.utils.embeds import green_embed, red_embed

from .config import FEED_CHANNEL_ID
from .embeds import build_profile_embed
from .i18n import t

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+|www\.\S+|\[.*?\]\(.*?\)", re.IGNORECASE)


def _contains_url(*texts: str) -> bool:
    return any(_URL_RE.search(text or "") for text in texts)


class DetailsModal(Modal):
    """Free-text step: about / looking-for / interests. Finalizes the post."""

    def __init__(self, bot: commands.Bot, prefs: dict, lang: str):
        super().__init__(title=t("modal_title", lang))
        self.bot = bot
        self.prefs = prefs
        self.lang = lang

        self.about = TextInput(
            style=TextStyle.paragraph,
            placeholder=t("modal_about_ph", lang),
            max_length=600,
            required=True,
        )
        self.want = TextInput(
            style=TextStyle.paragraph,
            placeholder=t("modal_want_ph", lang),
            max_length=600,
            required=True,
        )
        self.interests = TextInput(
            style=TextStyle.paragraph,
            placeholder=t("modal_interests_ph", lang),
            max_length=300,
            required=False,
        )
        self.add_item(Label(text=t("modal_about_label", lang), component=self.about))
        self.add_item(Label(text=t("modal_want_label", lang), component=self.want))
        self.add_item(Label(text=t("modal_interests_label", lang), component=self.interests))

    async def on_submit(self, interaction: Interaction) -> None:
        about = str(self.about.value)
        want = str(self.want.value)
        interests = str(self.interests.value) if self.interests.value else ""

        if _contains_url(about, want, interests):
            await interaction.response.send_message(
                embed=red_embed(t("error_no_urls", self.lang)), ephemeral=True,
            )
            return

        data = {
            **self.prefs,
            "user_id": interaction.user.id,
            "about_text": about,
            "want_text": want,
            "interests": interests,
            "lang": self.lang,
        }

        await interaction.response.send_message(
            embed=discord.Embed(description="⏳", color=discord.Color.blurple()),
            ephemeral=True,
        )

        feed = self.bot.get_channel(FEED_CHANNEL_ID)
        if not isinstance(feed, discord.abc.Messageable):
            logger.error("Langex feed channel %s unavailable", FEED_CHANNEL_ID)
            await interaction.edit_original_response(embed=red_embed(t("post_failed", self.lang)))
            return

        embed = build_profile_embed(data, interaction.user)

        # Replace any existing post message so there's one live post per user.
        existing = await self.bot.db.get_exchange_post(interaction.user.id)
        if existing:
            await _delete_message(self.bot, existing.get("channel_id"), existing.get("message_id"))

        try:
            msg = await feed.send(embed=embed)
        except discord.Forbidden:
            logger.error("Missing permissions to post in langex feed channel %s", FEED_CHANNEL_ID)
            await interaction.edit_original_response(embed=red_embed(t("post_failed", self.lang)))
            return
        except discord.HTTPException as exc:
            logger.error("Failed to post langex profile: %s", exc, exc_info=True)
            await interaction.edit_original_response(embed=red_embed(t("post_failed", self.lang)))
            return

        await self.bot.db.save_exchange_post(
            interaction.user.id, msg.id, feed.id, post_data=data,
        )
        await interaction.edit_original_response(embed=green_embed(t("posted_ok", self.lang)))

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        logger.error("Langex DetailsModal error: %s", error, exc_info=True)
        message = red_embed(t("generic_error", self.lang))
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=message)
            else:
                await interaction.response.send_message(embed=message, ephemeral=True)
        except discord.HTTPException:
            pass


async def _delete_message(bot: commands.Bot, channel_id: int | None, message_id: int | None) -> None:
    """Best-effort delete of a previously-posted profile message."""
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
