"""Atomicity of record_result: the daily-result insert and the stats bump must
commit or roll back together (no live Postgres — a fake pool records the calls).
"""
import asyncio

import pytest
from app.db import Database


class FakeTransaction:
    """Async-context transaction that records whether it exited with an error."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.tx_depth += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.conn.rolled_back = True
        else:
            self.conn.committed = True
        return False  # never suppress — a failing bump must propagate


class FakeConn:
    def __init__(self, *, fail_execute: bool):
        self.fail_execute = fail_execute
        self.tx_depth = 0
        self.committed = False
        self.rolled_back = False
        self.calls: list[str] = []

    def transaction(self):
        return FakeTransaction(self)

    async def fetchrow(self, query, *args):
        self.calls.append("fetchrow")
        # The INSERT ... RETURNING id (a new row); the streak SELECT returns None.
        if "INSERT INTO game_results" in query:
            assert self.tx_depth > 0, "insert must run inside the transaction"
            return {"id": 1}
        return None

    async def execute(self, query, *args):
        self.calls.append("execute")
        assert self.tx_depth > 0, "stats bump must run inside the transaction"
        if self.fail_execute:
            raise RuntimeError("simulated stats-bump failure")


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


def _db_with(conn: FakeConn) -> Database:
    db = Database("postgres://unused")
    db._pool = FakePool(conn)  # inject fake pool
    return db


async def _record(db: Database):
    return await db.record_result(
        game_key="wordle", user_id=42, mode="daily", won=True, puzzle_no=5,
        payload={"guesses_used": 3}, channel_id=None, guild_id=None,
    )


def test_insert_and_bump_share_one_committed_transaction():
    conn = FakeConn(fail_execute=False)
    inserted = asyncio.run(_record(_db_with(conn)))
    assert inserted is True
    assert conn.committed and not conn.rolled_back
    # Both the insert and the stats bump ran on the one connection.
    assert conn.calls == ["fetchrow", "fetchrow", "execute"]


def test_bump_failure_rolls_back_the_insert():
    conn = FakeConn(fail_execute=True)
    with pytest.raises(RuntimeError):
        asyncio.run(_record(_db_with(conn)))
    # The whole transaction rolled back — no orphaned daily row to block retry.
    assert conn.rolled_back and not conn.committed
