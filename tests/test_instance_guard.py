"""Only the newest deploy keeps the Discord session.

Skipped unless TEST_DATABASE_URL points at a server where the user can
create databases.
"""
import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import asyncpg
import pytest

from cogs.utils.instance_guard import InstanceGuard, StaleDeployment
from db import Database
from db.schema import initialize_schema


@pytest.fixture
async def fresh_db() -> AsyncIterator[tuple[Database, asyncpg.Connection]]:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to run instance guard integration tests")
    name = "instance_test_" + uuid4().hex
    admin = await asyncpg.connect(url)
    await admin.execute(f'CREATE DATABASE "{name}"')
    database = Database(url)
    database.pool = await asyncpg.create_pool(url, database=name, min_size=1, max_size=10)
    await initialize_schema(database.pool)
    raw = await asyncpg.connect(url, database=name)
    try:
        yield database, raw
    finally:
        await raw.close()
        # terminate, not close: a failed test can leave a guard's LISTEN connection checked out.
        database.pool.terminate()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def _guard(db: Database, version: int, **kwargs) -> tuple[InstanceGuard, asyncio.Event]:
    stepped_aside = asyncio.Event()

    async def on_superseded() -> None:
        stepped_aside.set()

    return InstanceGuard(db, version, f"sha{version}", on_superseded, **kwargs), stepped_aside


async def _events(raw: asyncpg.Connection, instance_id: str) -> list[str]:
    rows = await raw.fetch(
        "SELECT event FROM bot_instance_events WHERE instance_id = $1 ORDER BY id", instance_id,
    )
    return [row["event"] for row in rows]


async def test_claim_only_moves_forward(fresh_db) -> None:
    db, _raw = fresh_db
    assert await db.claim_instance(5, "a")
    assert not await db.claim_instance(4, "old")
    assert await db.claim_instance(5, "a-restarted")
    assert await db.claim_instance(6, "b")
    active = await db.active_instance()
    assert (active.deploy_version, active.instance_id) == (6, "b")


async def test_older_deploy_refuses_to_start(fresh_db) -> None:
    db, raw = fresh_db
    await db.claim_instance(6, "newer")
    guard, _ = _guard(db, 5)
    with pytest.raises(StaleDeployment):
        await guard.start()
    assert await _events(raw, guard.instance_id) == ["started", "refused_stale"]


async def test_newer_claim_notifies_older_instance(fresh_db) -> None:
    db, raw = fresh_db
    old, old_stepped_aside = _guard(db, 5, poll_seconds=60)
    await old.start()
    await old.claim()
    new, _ = _guard(db, 6, poll_seconds=60)
    await new.start()
    await new.claim()
    await asyncio.wait_for(old_stepped_aside.wait(), timeout=5)
    assert old.superseded and not new.superseded
    detail = await raw.fetchval(
        "SELECT detail->>'via' FROM bot_instance_events WHERE instance_id = $1 AND event = 'superseded'",
        old.instance_id,
    )
    assert detail == "notify"
    await old.stop()
    await new.stop()
    assert await _events(raw, old.instance_id) == ["started", "claimed", "superseded", "stopped"]


async def test_poll_catches_a_missed_notification(fresh_db) -> None:
    db, raw = fresh_db
    old, old_stepped_aside = _guard(db, 5, poll_seconds=0.05)
    await old.start()
    await old.claim()
    await raw.execute("UPDATE bot_instance SET deploy_version = 7, instance_id = 'silent'")
    await asyncio.wait_for(old_stepped_aside.wait(), timeout=5)
    via = await raw.fetchval(
        "SELECT detail->>'via' FROM bot_instance_events WHERE instance_id = $1 AND event = 'superseded'",
        old.instance_id,
    )
    assert via == "poll"
    await old.stop()


async def test_unversioned_instance_never_claims(fresh_db) -> None:
    db, raw = fresh_db
    guard, _ = _guard(db, 0)
    await guard.start()
    await guard.claim()
    await guard.stop()
    assert (await db.active_instance()).deploy_version == 0
    assert await _events(raw, guard.instance_id) == []
