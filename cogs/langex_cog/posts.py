"""Operations owning exchange profile messages and their database records."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from .components import build_profile_view

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


async def _delete_message(bot: Hablemos, post: dict) -> None:
    channel_id, message_id = post.get("channel_id"), post.get("message_id")
    if not channel_id or not message_id:
        return
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        logger.warning("Cannot clean up langex message %s: channel %s unavailable", message_id, channel_id)
        return
    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except discord.NotFound:
        return
    except discord.HTTPException:
        logger.exception("Failed to clean up langex message %s in channel %s", message_id, channel_id)


async def replace_exchange_post(
    bot: Hablemos, user: discord.User | discord.Member,
    feed: discord.abc.Messageable, data: dict,
) -> None:
    """Replace a user's live profile and persist its new message identity."""
    existing = await bot.db.get_exchange_post(user.id)
    message = await feed.send(view=build_profile_view(data, user))
    try:
        await bot.db.save_exchange_post(user.id, message.id, message.channel.id, post_data=data)
    except Exception:
        await _delete_message(bot, {"channel_id": message.channel.id, "message_id": message.id})
        raise
    if existing:
        await _delete_message(bot, existing)


async def delete_exchange_post(bot: Hablemos, user_id: int) -> bool:
    """Remove a stored profile and best-effort clean up its Discord message."""
    existing = await bot.db.get_exchange_post(user_id)
    if not existing:
        return False
    await _delete_message(bot, existing)
    await bot.db.delete_exchange_post(user_id)
    return True
