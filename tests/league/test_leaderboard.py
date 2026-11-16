"""League ranks and scores agree with the displayed PostgreSQL board."""
import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
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


async def test_complete_round_runs_once(league_db: Database) -> None:
    start = datetime.now(UTC)
    round_id = await league_db.create_round(4, start, start + timedelta(days=7))
    winners = [{
        'user_id': 10, 'username': '10', 'league_type': 'spanish',
        'rank': 1, 'total_score': 50, 'active_days': 3,
    }]
    end = start + timedelta(days=14)

    results = [{**winners[0], 'rank': 1}]
    first, second = await asyncio.gather(
        league_db.complete_round(round_id, winners, results, [10], 5, start, end),
        league_db.complete_round(round_id, winners, results, [10], 5, start, end),
    )

    assert [first, second].count(None) == 1
    current = await league_db.get_current_round()
    assert current is not None
    assert current['round_number'] == 5
    assert await league_db.get_last_round_role_recipients() == {10}
    async with league_db._pool().acquire() as conn:
        assert await conn.fetchval('SELECT COUNT(*) FROM league_round_winners') == 1
        assert await conn.fetchval('SELECT COUNT(*) FROM league_round_results') == 1
        assert await conn.fetchval('SELECT COUNT(*) FROM league_rounds') == 2


async def test_leave_and_unban_report_whether_anything_changed(league_db: Database) -> None:
    assert await league_db.leaderboard_leave(10) is False
    await league_db.leaderboard_join(10, '10', True, False)
    assert await league_db.leaderboard_leave(10) is True
    assert await league_db.leaderboard_leave(10) is False

    assert await league_db.leaderboard_unban_user(20) is False
    await league_db.leaderboard_ban_user(20, '20')
    banned = await league_db.get_all_banned_users()
    assert [row['user_id'] for row in banned] == [20]
    assert await league_db.leaderboard_unban_user(20) is True
    assert await league_db.leaderboard_unban_user(20) is False


async def test_counted_messages_add_level_xp(league_db: Database) -> None:
    start = datetime.now(UTC)
    round_id = await league_db.create_round(1, start, start + timedelta(days=7))
    await league_db.leaderboard_join(10, '10', True, False)

    first = await league_db.record_activity(10, points=20, round_id=round_id)
    second = await league_db.record_activity(10, points=10, round_id=round_id)

    assert (first.xp_before, first.xp_after, first.leveled_up) == (0, 20, False)
    assert (second.xp_before, second.xp_after, second.leveled_up) == (20, 30, True)
    assert second.cards_enabled
    today = datetime.now(UTC).date()
    assert (await league_db.get_league_profile(10, round_id, today)).progress.xp == 30
    assert (await league_db.get_league_profile(99, round_id, today)).progress.xp == 0

    await league_db.set_level_cards(10, False)
    third = await league_db.record_activity(10, points=1, round_id=round_id)
    assert (third.xp_after, third.cards_enabled) == (31, False)


async def _set_last_active(db: Database, user_id: int, day: date) -> None:
    async with db._pool().acquire() as conn:
        await conn.execute(
            'UPDATE league_levels SET last_active_date = $2 WHERE user_id = $1', user_id, day,
        )


async def test_streak_extends_daily_and_resets_after_a_gap(league_db: Database) -> None:
    start = datetime.now(UTC)
    today = start.date()
    round_id = await league_db.create_round(1, start, start + timedelta(days=7))
    await league_db.leaderboard_join(10, '10', True, False)

    await league_db.record_activity(10, round_id=round_id)
    await league_db.record_activity(10, round_id=round_id)
    profile = await league_db.get_league_profile(10, round_id, today)
    assert (profile.streak, profile.best_streak) == (1, 1)

    await _set_last_active(league_db, 10, today - timedelta(days=1))
    await league_db.record_activity(10, round_id=round_id)
    profile = await league_db.get_league_profile(10, round_id, today)
    assert (profile.streak, profile.best_streak) == (2, 2)

    await _set_last_active(league_db, 10, today - timedelta(days=3))
    lapsed = await league_db.get_league_profile(10, round_id, today)
    assert (lapsed.streak, lapsed.best_streak) == (0, 2)
    await league_db.record_activity(10, round_id=round_id)
    profile = await league_db.get_league_profile(10, round_id, today)
    assert (profile.streak, profile.best_streak) == (1, 2)


async def test_profile_standing_and_history(league_db: Database) -> None:
    start = datetime.now(UTC)
    today = start.date()
    old_round = await league_db.create_round(1, start - timedelta(days=7), start)
    for user_id in (10, 20, 30):
        await league_db.leaderboard_join(user_id, str(user_id), True, False)
    await league_db.leaderboard_join(40, '40', False, True)
    last_round = [
        {'user_id': 10, 'username': '10', 'league_type': 'spanish', 'rank': 3,
         'total_score': 40, 'active_days': 2},
    ]
    round_id = await league_db.complete_round(
        old_round, last_round, last_round, [10], 2, start, start + timedelta(days=7),
    )
    assert round_id is not None

    await league_db.record_activity(20, points=50, round_id=round_id)
    await league_db.record_activity(10, points=30, round_id=round_id)
    await league_db.record_activity(30, points=5, round_id=round_id)
    await league_db.record_activity(40, points=100, round_id=round_id)

    profile = await league_db.get_league_profile(10, round_id, today)
    standing = profile.standing
    assert standing is not None
    assert (standing.board, standing.rank, standing.combined_rank) == ('spanish', 2, 3)
    assert (standing.points, standing.active_days, standing.score) == (30, 1, 35)
    assert (standing.previous_rank, standing.movement) == (3, 1)
    assert (standing.above_gap, standing.below_gap) == (20, 25)
    assert profile.podiums == (0, 0, 1)
    assert profile.champion_weeks == 1
    assert profile.best_round == 40
    assert profile.daily_points == (0, 0, 0, 0, 0, 0, 30)

    await league_db.leaderboard_leave(10)
    assert (await league_db.get_league_profile(10, round_id, today)).standing is None
