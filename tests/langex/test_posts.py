"""Exchange lifecycle operations preserve live profiles when replacement fails."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.langex_cog.posts import delete_exchange_post, replace_exchange_post


def _bot():
    old_message = SimpleNamespace(delete=AsyncMock())
    channel = object.__new__(discord.TextChannel)
    channel.id = 10
    bot = SimpleNamespace(
        db=SimpleNamespace(
            get_exchange_post=AsyncMock(return_value={"channel_id": 10, "message_id": 20}),
            save_exchange_post=AsyncMock(), delete_exchange_post=AsyncMock(),
        ),
        get_channel=lambda _id: channel,
    )
    return bot, old_message, channel


@pytest.mark.asyncio
async def test_failed_replacement_keeps_existing_profile(monkeypatch) -> None:
    bot, old, _channel = _bot()
    monkeypatch.setattr(discord.TextChannel, "fetch_message", AsyncMock(return_value=old))
    feed = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr("cogs.langex_cog.posts.build_profile_view", lambda _data, _user: object())
    with pytest.raises(RuntimeError, match="unavailable"):
        await replace_exchange_post(bot, SimpleNamespace(id=7), feed, {})
    old.delete.assert_not_awaited()
    bot.db.save_exchange_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_replacement_saves_new_identity_and_removes_old_message(monkeypatch) -> None:
    bot, old, channel = _bot()
    monkeypatch.setattr(discord.TextChannel, "fetch_message", AsyncMock(return_value=old))
    feed = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=30, channel=channel)))
    monkeypatch.setattr("cogs.langex_cog.posts.build_profile_view", lambda _data, _user: object())
    await replace_exchange_post(bot, SimpleNamespace(id=7), feed, {"about_text": "Hello"})
    bot.db.save_exchange_post.assert_awaited_once_with(7, 30, 10, post_data={"about_text": "Hello"})
    old.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_removes_message_and_record(monkeypatch) -> None:
    bot, old, _channel = _bot()
    monkeypatch.setattr(discord.TextChannel, "fetch_message", AsyncMock(return_value=old))
    assert await delete_exchange_post(bot, 7)
    old.delete.assert_awaited_once()
    bot.db.delete_exchange_post.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_delete_logs_cleanup_failure_and_still_removes_record(monkeypatch, caplog) -> None:
    bot, old, _channel = _bot()
    old.delete.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "denied")
    monkeypatch.setattr(discord.TextChannel, "fetch_message", AsyncMock(return_value=old))
    assert await delete_exchange_post(bot, 7)
    bot.db.delete_exchange_post.assert_awaited_once_with(7)
    assert "Failed to clean up langex message 20" in caplog.text
