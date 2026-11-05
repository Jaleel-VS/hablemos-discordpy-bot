"""Conversation quota behavior against an isolated PostgreSQL database."""
import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import asyncpg
import pytest

from db import Database
from db.schema import initialize_schema


@pytest.fixture
async def conversation_db() -> AsyncIterator[Database]:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to run conversation quota integration tests")
    name = "conversation_test_" + uuid4().hex
    admin = await asyncpg.connect(url)
    database = Database(url)
    await admin.execute(f'CREATE DATABASE "{name}"')
    try:
        database.pool = await asyncpg.create_pool(url, database=name)
        await initialize_schema(database._pool())
        yield database
    finally:
        await database.close()
        await admin.execute(f'DROP DATABASE "{name}"')
        await admin.close()


async def test_concurrent_reservations_honor_quota(conversation_db: Database) -> None:
    results = await asyncio.gather(*(conversation_db.try_reserve_daily_usage(7, 2) for _ in range(8)))
    assert results.count(True) == 2
    assert await conversation_db.get_daily_usage_remaining(7, 2) == 0
    assert await conversation_db.try_reserve_daily_usage(8, 2)


async def test_refund_restores_one_slot_without_negative_usage(conversation_db: Database) -> None:
    assert await conversation_db.try_reserve_daily_usage(7, 2)
    await conversation_db.refund_daily_usage(7)
    assert await conversation_db.get_daily_usage_remaining(7, 2) == 2
    await conversation_db.refund_daily_usage(7)
    assert await conversation_db.get_daily_usage_remaining(7, 2) == 2
    assert await conversation_db.try_reserve_daily_usage(7, 2)
