"""Database mixin for reading Activity game results.

The **Activity** service owns the ``game_results``/``game_stats`` schema (it
creates the tables on boot; see ``activity/backend/app/db.py``). The bot only
*reads* finished daily results here to post them to a channel and marks them
posted. To avoid schema duplication/drift, the bot never creates these tables —
so every method tolerates the table not existing yet (returns empty / no-op)
rather than raising, which matters on a fresh environment where the Activity
hasn't booted yet.
"""
import contextlib

import asyncpg

from db import DatabaseMixin


class GameResultsMixin(DatabaseMixin):
    async def fetch_unposted_game_results(self, limit: int = 20) -> list:
        """Daily results not yet posted to a channel, oldest first.

        Returns ``[]`` if the table doesn't exist yet (Activity not deployed).
        """
        try:
            return await self._fetch(
                '''
                SELECT id, game_key, user_id, mode, won, puzzle_no,
                       payload, channel_id, guild_id, created_at
                FROM game_results
                WHERE posted_at IS NULL AND mode = 'daily'
                ORDER BY created_at
                LIMIT $1
                ''',
                limit,
            )
        except asyncpg.UndefinedTableError:
            return []

    async def mark_game_result_posted(self, result_id: int) -> None:
        """Mark a result row as posted. No-op if the table is missing."""
        with contextlib.suppress(asyncpg.UndefinedTableError):
            await self._execute(
                'UPDATE game_results SET posted_at = NOW() WHERE id = $1',
                result_id,
            )

    # ── owner-facing stats reads (see $activity_stats) ──────────────────────
    # These are the read side of the Activity's own tables. Like the poller
    # methods above they tolerate the tables not existing yet (Activity not
    # deployed) by returning zero-valued results, so a fresh environment or a
    # bot-only deploy never errors.

    async def activity_totals_by_game(self) -> list:
        """Per-game aggregate counts across all recorded results.

        One row per ``game_key``: total games, unique players, daily/free
        split, wins, and how many daily rows are still awaiting posting.
        Empty list if the table doesn't exist yet.
        """
        try:
            return await self._fetch(
                '''
                SELECT
                    game_key,
                    COUNT(*)                                        AS games,
                    COUNT(DISTINCT user_id)                         AS players,
                    COUNT(*) FILTER (WHERE mode = 'daily')          AS daily,
                    COUNT(*) FILTER (WHERE mode <> 'daily')         AS freeplay,
                    COUNT(*) FILTER (WHERE won)                     AS wins,
                    COUNT(*) FILTER (
                        WHERE mode = 'daily' AND posted_at IS NULL
                    )                                               AS pending
                FROM game_results
                GROUP BY game_key
                ORDER BY games DESC
                ''',
            )
        except asyncpg.UndefinedTableError:
            return []

    async def activity_pending_health(self) -> dict:
        """Results-poster backlog: count of unposted daily rows + oldest age.

        Returns ``{"pending": 0, "oldest": None}`` when nothing is pending or
        the table is missing — callers get concrete values, never ``None`` for
        the count.
        """
        try:
            row = await self._fetchrow(
                '''
                SELECT COUNT(*) AS pending, MIN(created_at) AS oldest
                FROM game_results
                WHERE posted_at IS NULL AND mode = 'daily'
                ''',
            )
        except asyncpg.UndefinedTableError:
            return {"pending": 0, "oldest": None}
        if row is None:
            return {"pending": 0, "oldest": None}
        return {"pending": row["pending"], "oldest": row["oldest"]}

    async def activity_top_streaks(self, *, game_key: str, limit: int = 10) -> list:
        """Top players for a game by max daily streak (tie-break: current).

        Reads ``game_stats``. Empty list if the table doesn't exist yet.
        """
        try:
            return await self._fetch(
                '''
                SELECT user_id, games, wins, current_streak, max_streak
                FROM game_stats
                WHERE game_key = $1 AND games > 0
                ORDER BY max_streak DESC, current_streak DESC, wins DESC
                LIMIT $2
                ''',
                game_key, limit,
            )
        except asyncpg.UndefinedTableError:
            return []

    async def activity_user_stats(self, *, game_key: str, user_id: int) -> dict | None:
        """One player's daily stats for a game, or ``None`` if they've never
        played it (or the table is missing).

        ``None`` here is a real "no rows" signal the caller renders as a
        friendly message, not an error — it's normalized at this boundary so
        callers don't touch asyncpg exceptions.
        """
        try:
            row = await self._fetchrow(
                '''
                SELECT user_id, games, wins, current_streak, max_streak,
                       last_puzzle_no, distribution
                FROM game_stats
                WHERE game_key = $1 AND user_id = $2
                ''',
                game_key, user_id,
            )
        except asyncpg.UndefinedTableError:
            return None
        return dict(row) if row is not None else None
