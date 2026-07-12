"""Database access for the Activity backend.

A small, self-contained asyncpg layer that connects to the **same** PostgreSQL
the gateway bot uses (via ``DATABASE_URL``). It intentionally does not import
the bot's ``db/`` package — the Activity is a separate service/deploy — but it
mirrors the repo's conventions: a thin pool wrapper with ``_fetch``/``_execute``
helpers, idempotent schema creation on connect, and query methods that
normalize ``None`` at the boundary so callers get concrete values.

Tables are **game-agnostic**, keyed by ``game_key``, so every game (Wordle
first) and the Phase 2 results poster reuse the same shape:

* ``game_results`` — one row per finished game (payload JSONB holds the
  game-specific result card). ``posted_at`` is NULL until the bot posts it.
* ``game_stats``   — per (game_key, user_id) aggregates for daily-mode play:
  games, wins, current/max streak, and a guess-distribution JSONB.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS game_results (
    id           BIGSERIAL PRIMARY KEY,
    game_key     TEXT        NOT NULL,
    user_id      BIGINT      NOT NULL,
    mode         TEXT        NOT NULL,
    won          BOOLEAN     NOT NULL,
    puzzle_no    INTEGER,
    payload      JSONB       NOT NULL,
    channel_id   BIGINT,
    guild_id     BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    posted_at    TIMESTAMPTZ
);

-- One daily result per user per puzzle per game (freeplay rows have NULL
-- puzzle_no and are not constrained). Enables idempotent daily submission.
CREATE UNIQUE INDEX IF NOT EXISTS game_results_daily_uniq
    ON game_results (game_key, user_id, puzzle_no)
    WHERE puzzle_no IS NOT NULL AND mode = 'daily';

-- Fast lookup for the Phase 2 poller: unposted daily results, oldest first.
CREATE INDEX IF NOT EXISTS game_results_unposted
    ON game_results (created_at)
    WHERE posted_at IS NULL AND mode = 'daily';

CREATE TABLE IF NOT EXISTS game_stats (
    game_key       TEXT   NOT NULL,
    user_id        BIGINT NOT NULL,
    games          INTEGER NOT NULL DEFAULT 0,
    wins           INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    max_streak     INTEGER NOT NULL DEFAULT 0,
    last_puzzle_no INTEGER,
    distribution   JSONB  NOT NULL DEFAULT '{}'::jsonb,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (game_key, user_id)
);
"""


def compute_streak(
    *,
    prev_streak: int,
    last_puzzle_no: int | None,
    won: bool,
    puzzle_no: int | None,
) -> int:
    """Return the new current-streak after a daily result.

    A win on the puzzle immediately after ``last_puzzle_no`` extends the
    streak; any other win (re)starts it at 1; a loss resets it to 0. Pure
    function so the state machine can be tested without a database.
    """
    if not won:
        return 0
    if last_puzzle_no is not None and puzzle_no == last_puzzle_no + 1:
        return prev_streak + 1
    return 1


def distribution_key(*, won: bool, guesses_used: int | None) -> str:
    """Distribution bucket for a result: guess count for wins, else ``"X"``."""
    return str(guesses_used) if (won and guesses_used) else "X"


class Database:
    """Owns the asyncpg pool and all query methods for the Activity."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self, *, retries: int = 5) -> None:
        """Create the pool and ensure the schema, retrying transient failures.

        Railway's internal DNS (``*.railway.internal``) can lag briefly on a
        cold start, so we back off and retry rather than give up on the first
        connection error.
        """
        for attempt in range(1, retries + 1):
            try:
                self._pool = await asyncpg.create_pool(
                    self._url,
                    min_size=1,
                    max_size=5,
                    command_timeout=30,
                    statement_cache_size=0,
                )
                async with self._pool.acquire() as conn:
                    await conn.execute(_SCHEMA)
                logger.info("Activity DB pool created and schema ensured")
                return
            except Exception as exc:  # noqa: BLE001 — retry any connect failure
                wait = min(2 ** attempt, 15)
                logger.warning("DB connect attempt %d/%d failed: %s (retry in %ss)",
                               attempt, retries, exc, wait)
                if attempt == retries:
                    raise
                await asyncio.sleep(wait)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            logger.info("Activity DB pool closed")

    def _p(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("DB pool not initialized; call connect() first")
        return self._pool

    # ── results ───────────────────────────────────────────────────────────

    async def record_result(
        self,
        *,
        game_key: str,
        user_id: int,
        mode: str,
        won: bool,
        puzzle_no: int | None,
        payload: dict[str, Any],
        channel_id: int | None,
        guild_id: int | None,
    ) -> bool:
        """Insert a finished-game result.

        Returns ``True`` if a new row was inserted, ``False`` if this was a
        duplicate daily submission (already recorded for this puzzle/user).
        Daily stats are only updated on a genuinely new insert.

        The insert and the stats bump run in **one transaction**: if the bump
        fails, the insert rolls back too. Otherwise the unique daily row would
        persist while the streak update was lost, permanently blocking the
        retry that would fix it.
        """
        async with self._p().acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO game_results
                    (game_key, user_id, mode, won, puzzle_no, payload,
                     channel_id, guild_id)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                ON CONFLICT (game_key, user_id, puzzle_no)
                    WHERE puzzle_no IS NOT NULL AND mode = 'daily'
                DO NOTHING
                RETURNING id
                """,
                game_key, user_id, mode, won, puzzle_no, json.dumps(payload),
                channel_id, guild_id,
            )
            inserted = row is not None
            if inserted and mode == "daily":
                await self._bump_daily_stats(
                    conn, game_key=game_key, user_id=user_id, won=won,
                    puzzle_no=puzzle_no, guesses_used=payload.get("guesses_used"),
                )
            return inserted

    async def has_daily_result(
        self, *, game_key: str, user_id: int, puzzle_no: int,
    ) -> bool:
        """Whether this user already finished this game's daily puzzle.

        Used to refuse a second daily ``/start`` — the daily is a fixed,
        deterministic sequence, so replaying it would let a player retry for a
        better score (and against the honor-system leaderboard). Returns
        ``False`` for any freeplay row (those carry a NULL ``puzzle_no``).
        """
        row = await self._p().fetchrow(
            """
            SELECT 1
            FROM game_results
            WHERE game_key = $1 AND user_id = $2
              AND puzzle_no = $3 AND mode = 'daily'
            LIMIT 1
            """,
            game_key, user_id, puzzle_no,
        )
        return row is not None

    async def fetch_unposted_daily(self, limit: int = 20) -> list[dict[str, Any]]:
        """Daily results not yet posted to a channel, oldest first (Phase 2)."""
        rows = await self._p().fetch(
            """
            SELECT id, game_key, user_id, mode, won, puzzle_no,
                   payload, channel_id, guild_id, created_at
            FROM game_results
            WHERE posted_at IS NULL AND mode = 'daily'
            ORDER BY created_at
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def mark_posted(self, result_id: int) -> None:
        """Mark a result row as posted (Phase 2)."""
        await self._p().execute(
            "UPDATE game_results SET posted_at = NOW() WHERE id = $1",
            result_id,
        )

    # ── stats ─────────────────────────────────────────────────────────────

    async def get_stats(self, *, game_key: str, user_id: int) -> dict[str, Any]:
        """Per-user daily stats. Returns a zero-valued dict if none exist.

        Never returns ``None`` — the absence of a row is a real "no games yet"
        state, modeled as zeros so the UI has nothing to branch on.
        """
        row = await self._p().fetchrow(
            """
            SELECT games, wins, current_streak, max_streak, distribution
            FROM game_stats
            WHERE game_key = $1 AND user_id = $2
            """,
            game_key, user_id,
        )
        if row is None:
            return {
                "games": 0, "wins": 0, "current_streak": 0,
                "max_streak": 0, "distribution": {},
            }
        data = dict(row)
        dist = data.get("distribution")
        data["distribution"] = json.loads(dist) if isinstance(dist, str) else (dist or {})
        return data

    async def _bump_daily_stats(
        self,
        conn: asyncpg.Connection,
        *,
        game_key: str,
        user_id: int,
        won: bool,
        puzzle_no: int | None,
        guesses_used: int | None,
    ) -> None:
        """Update aggregates + streak for a new daily result.

        Runs on the caller's connection inside the caller's transaction (see
        :meth:`record_result`) so the result insert and this bump commit or roll
        back together.

        Streak logic: a win on the puzzle immediately after ``last_puzzle_no``
        extends the streak; any other win (re)starts it at 1; a loss resets it
        to 0. ``distribution`` counts wins by guess count.
        """
        cur = await conn.fetchrow(
            """
            SELECT current_streak, max_streak, last_puzzle_no
            FROM game_stats
            WHERE game_key = $1 AND user_id = $2
            FOR UPDATE
            """,
            game_key, user_id,
        )
        prev_streak = cur["current_streak"] if cur else 0
        prev_max = cur["max_streak"] if cur else 0
        last_no = cur["last_puzzle_no"] if cur else None

        new_streak = compute_streak(
            prev_streak=prev_streak, last_puzzle_no=last_no,
            won=won, puzzle_no=puzzle_no,
        )
        new_max = max(prev_max, new_streak)
        dist_key = distribution_key(won=won, guesses_used=guesses_used)

        await conn.execute(
            """
            INSERT INTO game_stats
                (game_key, user_id, games, wins, current_streak,
                 max_streak, last_puzzle_no, distribution, updated_at)
            VALUES ($1, $2, 1, $3, $4, $5, $6,
                    jsonb_build_object($7::text, 1), NOW())
            ON CONFLICT (game_key, user_id) DO UPDATE SET
                games          = game_stats.games + 1,
                wins           = game_stats.wins + $3,
                current_streak = $4,
                max_streak     = $5,
                last_puzzle_no = $6,
                distribution   = jsonb_set(
                    game_stats.distribution,
                    ARRAY[$7::text],
                    to_jsonb(
                        COALESCE((game_stats.distribution->>$7)::int, 0) + 1
                    )
                ),
                updated_at     = NOW()
            """,
            game_key, user_id, 1 if won else 0, new_streak, new_max,
            puzzle_no, dist_key,
        )
