"""Introduction acceptance is shared by channel tracking and modal posts."""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import discord
import pytest

from cogs.intro_cog.config import INTRO_CHANNEL_ID
from cogs.intro_cog.main import IntroductionTracker
from cogs.introduce_cog.config import INTRODUCTIONS_CHANNEL_ID
from cogs.introduce_cog.modals import _post_intro
from db import Database


def _bot(accepted: bool, *, enabled: bool = True):
    channel = object.__new__(discord.TextChannel)
    channel.id = INTRO_CHANNEL_ID
    bot = SimpleNamespace(
        db=SimpleNamespace(
            get_feature_setting=AsyncMock(return_value=enabled),
            get_intro_exempt_users=AsyncMock(return_value=set()),
            record_introduction=AsyncMock(return_value=accepted),
            record_accepted_introduction=AsyncMock(),
            get_introduction_count=AsyncMock(return_value=2),
        ),
        get_channel=lambda _id: channel,
        settings=SimpleNamespace(),
    )
    return bot, channel


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
async def test_tracker_only_removes_rejected_attempts(accepted: bool) -> None:
    bot, channel = _bot(accepted)
    tracker = IntroductionTracker(bot)
    tracker._handle_duplicate_intro = AsyncMock()
    message = SimpleNamespace(author=SimpleNamespace(id=7, bot=False, roles=[]), channel=channel)
    await tracker.on_message(message)
    bot.db.record_introduction.assert_awaited_once_with(7, 90)
    assert tracker._handle_duplicate_intro.await_count == (0 if accepted else 1)


@pytest.mark.asyncio
async def test_modal_always_posts_and_records_accepted_intro(monkeypatch) -> None:
    bot, _channel = _bot(False)
    monkeypatch.setattr(discord.TextChannel, "send", AsyncMock())
    interaction = SimpleNamespace(
        client=bot, user=SimpleNamespace(id=7, roles=[]),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    embed = discord.Embed(title="intro")
    await _post_intro(interaction, embed, INTRODUCTIONS_CHANNEL_ID, "en")
    bot.db.record_accepted_introduction.assert_awaited_once_with(7)
    bot.db.record_introduction.assert_not_awaited()
    assert discord.TextChannel.send.await_args_list[0].kwargs["embed"] is embed


@pytest.mark.asyncio
async def test_disabled_tracker_leaves_channel_posts_unrecorded() -> None:
    bot, channel = _bot(False, enabled=False)
    tracker = IntroductionTracker(bot)
    message = SimpleNamespace(author=SimpleNamespace(id=7, bot=False, roles=[]), channel=channel)
    await tracker.on_message(message)
    bot.db.record_introduction.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_attempts_do_not_extend_accepted_cooldown() -> None:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to run introduction storage integration tests")
    database = Database(url)
    database.pool = await asyncpg.create_pool(url, min_size=1, max_size=1)
    try:
        async with database.pool.acquire() as conn:
            await conn.execute("""CREATE TEMP TABLE introductions (
                id SERIAL PRIMARY KEY, user_id BIGINT, posted_at TIMESTAMPTZ, accepted BOOLEAN
            )""")
        assert await database.record_introduction(7, 90)
        await database._execute("UPDATE introductions SET posted_at = NOW() - INTERVAL '89 days'")
        assert not await database.record_introduction(7, 90)
        await database._execute("""UPDATE introductions
            SET posted_at = NOW() - INTERVAL '91 days' WHERE accepted""")
        assert await database.record_introduction(7, 90)
        assert await database.get_introduction_count(7) == 3
    finally:
        await database.close()
