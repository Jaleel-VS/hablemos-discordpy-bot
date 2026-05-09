"""Database mixin for crossword game state.

Tracks in-flight games (for interrupt recovery on restart) and the
normalized game/participant/word-event tables that power metrics.
"""
import uuid
from datetime import datetime

from db import DatabaseMixin


class CrosswordMixin(DatabaseMixin):
    # ── active-game snapshot (interrupt recovery) ─────────────────────────

    async def crossword_save_active_game(
        self,
        *,
        channel_id: int,
        starter_id: int,
        guild_id: int | None,
        is_dm: bool,
        message_id: int | None,
        language: str,
        difficulty: str,
        total_words: int,
        game_id: uuid.UUID,
    ) -> None:
        """Record a newly started crossword game."""
        await self._execute(
            '''
            INSERT INTO crossword_active_games
                (channel_id, starter_id, guild_id, is_dm, message_id,
                 language, difficulty, total_words, solved_count,
                 game_id, started_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, $9, NOW(), NOW())
            ON CONFLICT (channel_id) DO UPDATE
            SET starter_id   = EXCLUDED.starter_id,
                guild_id     = EXCLUDED.guild_id,
                is_dm        = EXCLUDED.is_dm,
                message_id   = EXCLUDED.message_id,
                language     = EXCLUDED.language,
                difficulty   = EXCLUDED.difficulty,
                total_words  = EXCLUDED.total_words,
                solved_count = 0,
                game_id      = EXCLUDED.game_id,
                started_at   = NOW(),
                updated_at   = NOW()
            ''',
            channel_id, starter_id, guild_id, is_dm, message_id,
            language, difficulty, total_words, game_id,
        )

    async def crossword_bump_solved(self, channel_id: int) -> None:
        """Increment ``solved_count`` for an active game. No-op if missing."""
        await self._execute(
            '''
            UPDATE crossword_active_games
            SET solved_count = solved_count + 1, updated_at = NOW()
            WHERE channel_id = $1
            ''',
            channel_id,
        )

    async def crossword_clear_active_game(self, channel_id: int) -> None:
        """Remove the active-game row (called on natural end or recovery)."""
        await self._execute(
            'DELETE FROM crossword_active_games WHERE channel_id = $1',
            channel_id,
        )

    async def crossword_get_all_active_games(self) -> list:
        """Return all active-game rows (for interrupt recovery on startup)."""
        return await self._fetch(
            'SELECT * FROM crossword_active_games ORDER BY started_at'
        )

    # ── game outcome persistence (tier 1 + 2) ─────────────────────────────

    async def crossword_persist_game_outcome(
        self,
        *,
        game_id: uuid.UUID,
        guild_id: int | None,
        channel_id: int,
        starter_id: int,
        difficulty: str,
        language: str,
        total_words: int,
        words_solved: int,
        hints_used: int,
        completion: str,
        started_at: datetime,
        ended_at: datetime,
        elapsed_seconds: float,
        participants: list[dict],
        word_events: list[dict],
    ) -> None:
        """Persist a finished game as game + participants + word events.

        Runs in a single transaction so either everything lands or nothing
        does (no orphaned game rows on partial failure).

        ``participants`` entries: ``user_id``, ``display_name``,
        ``words_solved``, ``is_starter``.

        ``word_events`` entries: ``word``, ``solved``, ``solved_by``,
        ``seconds_to_solve``, ``had_hint``.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute(
                '''
                INSERT INTO crossword_games
                    (game_id, guild_id, channel_id, starter_id,
                     difficulty, language, total_words, words_solved,
                     hints_used, completion,
                     started_at, ended_at, elapsed_seconds)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13)
                ON CONFLICT (game_id) DO NOTHING
                ''',
                game_id, guild_id, channel_id, starter_id,
                difficulty, language, total_words, words_solved,
                hints_used, completion,
                started_at, ended_at, elapsed_seconds,
            )

            if participants:
                await conn.executemany(
                    '''
                    INSERT INTO crossword_participants
                        (game_id, user_id, display_name, words_solved, is_starter)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (game_id, user_id) DO NOTHING
                    ''',
                    [
                        (
                            game_id,
                            p["user_id"],
                            p["display_name"],
                            p["words_solved"],
                            p["is_starter"],
                        )
                        for p in participants
                    ],
                )

            if word_events:
                await conn.executemany(
                    '''
                    INSERT INTO crossword_word_events
                        (game_id, word, language, difficulty,
                         solved, solved_by, seconds_to_solve, had_hint)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ''',
                    [
                        (
                            game_id,
                            e["word"],
                            language,
                            difficulty,
                            e["solved"],
                            e.get("solved_by"),
                            e.get("seconds_to_solve"),
                            e.get("had_hint", False),
                        )
                        for e in word_events
                    ],
                )

    async def crossword_record_interrupted(
        self,
        *,
        game_id: uuid.UUID | None,
        guild_id: int | None,
        channel_id: int,
        starter_id: int,
        difficulty: str,
        language: str,
        total_words: int,
        words_solved: int,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        """Log an interrupted-by-restart game as a bare games row.

        No participant or word-event data is available at recovery time,
        so only the crossword_games row is written.
        """
        gid = game_id or uuid.uuid4()
        elapsed = max(0.0, (ended_at - started_at).total_seconds())
        await self._execute(
            '''
            INSERT INTO crossword_games
                (game_id, guild_id, channel_id, starter_id,
                 difficulty, language, total_words, words_solved,
                 hints_used, completion,
                 started_at, ended_at, elapsed_seconds)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, 'interrupted',
                    $9, $10, $11)
            ON CONFLICT (game_id) DO NOTHING
            ''',
            gid, guild_id, channel_id, starter_id,
            difficulty, language, total_words, words_solved,
            started_at, ended_at, elapsed,
        )

    # ── stats helpers (read from the new tables) ──────────────────────────

    async def crossword_get_stats(self, days: int | None = 30) -> dict:
        """Return aggregate crossword stats over a window.

        Reads from the normalized crossword_games/crossword_participants
        tables. ``days=None`` means lifetime.
        """
        if days is None:
            where_games = ""
            where_parts = ""
            args: tuple = ()
        else:
            where_games = "WHERE started_at >= NOW() - MAKE_INTERVAL(days => $1)"
            where_parts = (
                "WHERE game_id IN "
                "(SELECT game_id FROM crossword_games "
                "WHERE started_at >= NOW() - MAKE_INTERVAL(days => $1))"
            )
            args = (days,)

        totals_row = await self._fetchrow(
            f'''
            SELECT
                COUNT(*)                                             AS games,
                COUNT(*) FILTER (WHERE completion = 'completed')     AS completed,
                COUNT(*) FILTER (WHERE completion = 'timeout')       AS timed_out,
                COUNT(*) FILTER (WHERE completion = 'quit')          AS quit,
                COUNT(*) FILTER (WHERE completion = 'interrupted')   AS interrupted,
                COALESCE(SUM(words_solved), 0)::int                  AS total_words_solved,
                COALESCE(AVG(words_solved::float / NULLIF(total_words, 0)), 0)::float
                                                                     AS avg_completion_ratio,
                COALESCE(AVG(elapsed_seconds) FILTER (WHERE completion = 'completed'), 0)::float
                                                                     AS avg_completion_seconds,
                COALESCE(SUM(hints_used), 0)::int                    AS total_hints,
                COALESCE(AVG(hints_used), 0)::float                  AS avg_hints_per_game
            FROM crossword_games
            {where_games}
            ''',
            *args,
        )

        players_row = await self._fetchrow(
            f'''
            SELECT COUNT(DISTINCT user_id) AS unique_players,
                   COALESCE(AVG(per_game.participants), 0)::float AS avg_participants_per_game
            FROM crossword_participants
            JOIN (
                SELECT game_id, COUNT(*)::int AS participants
                FROM crossword_participants
                GROUP BY game_id
            ) per_game USING (game_id)
            {where_parts}
            ''',
            *args,
        )

        breakdown = await self._fetch(
            f'''
            SELECT difficulty, language,
                   COUNT(*) AS games,
                   COUNT(*) FILTER (WHERE completion = 'completed') AS completed
            FROM crossword_games
            {where_games}
            GROUP BY difficulty, language
            ORDER BY games DESC
            ''',
            *args,
        )

        return {
            "totals": dict(totals_row) if totals_row else {},
            "players": dict(players_row) if players_row else {},
            "breakdown": [dict(r) for r in breakdown],
        }

    async def crossword_get_top_solvers(
        self, days: int | None = 30, limit: int = 10, guild_id: int | None = None,
    ) -> list:
        """Top players by total words solved over a window.

        ``guild_id`` scopes the leaderboard to a single guild (used by the
        public ``$cwl`` leaderboard). ``None`` includes every game, which
        is what the admin ``$cwstats`` view wants.
        """
        args: list = []
        joins = ""
        wheres: list[str] = []

        if days is not None:
            args.append(days)
            wheres.append(
                f"g.started_at >= NOW() - MAKE_INTERVAL(days => ${len(args)})"
            )
        if guild_id is not None:
            args.append(guild_id)
            wheres.append(f"g.guild_id = ${len(args)}")

        if wheres:
            joins = (
                "JOIN crossword_games g ON g.game_id = p.game_id AND "
                + " AND ".join(wheres)
            )
        elif days is None and guild_id is None:
            # No filters at all — skip the join entirely for a lifetime,
            # cross-guild view (the original fast path).
            joins = ""
        else:  # pragma: no cover — defensive; above branches cover both cases
            joins = ""

        args.append(limit)
        limit_placeholder = f"${len(args)}"

        return await self._fetch(
            f'''
            SELECT p.user_id,
                   MAX(p.display_name)       AS display_name,
                   SUM(p.words_solved)::int  AS words_solved,
                   COUNT(*)::int             AS games,
                   COUNT(*) FILTER (WHERE p.is_starter)::int AS games_started
            FROM crossword_participants p
            {joins}
            GROUP BY p.user_id
            HAVING SUM(p.words_solved) > 0
            ORDER BY words_solved DESC, games DESC
            LIMIT {limit_placeholder}
            ''',
            *args,
        )

    # ── word-level (tier 2) ───────────────────────────────────────────────

    async def crossword_get_word_difficulty(
        self,
        *,
        language: str | None = None,
        order: str = "hardest",
        min_appearances: int = 3,
        limit: int = 15,
        days: int | None = None,
    ) -> list:
        """Return per-word solve-rate stats.

        ``order`` is 'hardest' (lowest solve rate first) or 'easiest'
        (highest first). ``language`` filters to 'es' or 'en' if given.
        """
        args: list = []
        wheres: list[str] = []
        if language is not None:
            args.append(language)
            wheres.append(f"language = ${len(args)}")
        if days is not None:
            args.append(days)
            wheres.append(
                f"game_id IN (SELECT game_id FROM crossword_games "
                f"WHERE started_at >= NOW() - MAKE_INTERVAL(days => ${len(args)}))"
            )
        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

        args.append(min_appearances)
        having_placeholder = f"${len(args)}"
        args.append(limit)
        limit_placeholder = f"${len(args)}"

        direction = "ASC" if order == "hardest" else "DESC"
        return await self._fetch(
            f'''
            SELECT word, language, difficulty,
                   COUNT(*)::int                                        AS appearances,
                   SUM(CASE WHEN solved THEN 1 ELSE 0 END)::int         AS solves,
                   AVG(CASE WHEN solved THEN 1.0 ELSE 0.0 END)::float   AS solve_rate,
                   AVG(seconds_to_solve) FILTER (WHERE solved)::float   AS avg_solve_seconds,
                   SUM(CASE WHEN had_hint THEN 1 ELSE 0 END)::int       AS hint_assists
            FROM crossword_word_events
            {where_sql}
            GROUP BY word, language, difficulty
            HAVING COUNT(*) >= {having_placeholder}
            ORDER BY solve_rate {direction}, appearances DESC
            LIMIT {limit_placeholder}
            ''',
            *args,
        )

    async def crossword_get_unseen_words(
        self, *, language: str, limit: int = 20,
    ) -> list:
        """Words in the word-list that have never appeared in any game."""
        word_col = "word_es" if language == "es" else "word_en"
        return await self._fetch(
            f'''
            SELECT {word_col} AS word, difficulty, theme
            FROM crossword_words w
            WHERE NOT EXISTS (
                SELECT 1 FROM crossword_word_events e
                WHERE e.language = $1 AND e.word = w.{word_col}
            )
            ORDER BY difficulty, {word_col}
            LIMIT $2
            ''',
            language, limit,
        )
