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
