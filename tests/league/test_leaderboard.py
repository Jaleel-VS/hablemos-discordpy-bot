"""League ranks and scores agree with the displayed PostgreSQL board."""
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest

from cogs.league_cog.config import SCORING
from db import Database
from db.schema import initialize_schema


@pytest.fixture
async def league_db() -> AsyncIterator[Database]:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to run league ranking integration tests")
    name = "league_test_" + uuid4().hex
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


@pytest.mark.parametrize("board", ["combined", "spanish", "english"])
async def test_user_rank_matches_tied_board(league_db: Database, board: str) -> None:
    start = datetime.now(UTC)
    round_id = await league_db.create_round(1, start, start + timedelta(days=7))
    for user_id in [30, 10, 20]:
        await league_db.leaderboard_join(user_id, str(user_id), True, True)
        await league_db.record_activity(user_id, points=3, round_id=round_id)

    rows = await league_db.get_leaderboard(board, round_id=round_id)
    assert [(row["user_id"], row["rank"]) for row in rows] == [(10, 1), (20, 2), (30, 3)]
    for expected_rank, user_id in enumerate([10, 20, 30], start=1):
        stats = await league_db.get_user_stats(user_id, round_id)
        assert stats is not None
        assert stats[f"rank_{board}"] == expected_rank


async def test_configured_active_day_bonus_changes_scores_and_order(
    league_db: Database, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("db.leaderboard.SCORING", replace(SCORING, ACTIVE_DAY_BONUS_MULTIPLIER=9))
    start = datetime.now(UTC)
    round_id = await league_db.create_round(1, start, start + timedelta(days=7))
    for user_id in [10, 20]:
        await league_db.leaderboard_join(user_id, str(user_id), True, True)
    created = start.replace(tzinfo=None)
    async with league_db._pool().acquire() as conn:
        await conn.executemany(
            """INSERT INTO leaderboard_activity (user_id, activity_type, points, round_id, created_at)
               VALUES ($1, 'message', $2, $3, $4)""",
            [
                (10, 8, round_id, created),
                (20, 1, round_id, created),
                (20, 1, round_id, created - timedelta(days=1)),
            ],
        )

    rows = await league_db.get_leaderboard("combined", round_id=round_id)
    assert [(row["user_id"], row["total_score"]) for row in rows] == [(20, 20), (10, 17)]
    stats = await league_db.get_user_stats(20, round_id)
    assert stats is not None
    assert stats["total_score"] == 20
    assert stats["rank_combined"] == 1
    assert stats["rank_spanish"] == 1
    assert stats["rank_english"] == 1
