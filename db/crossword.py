"""Database mixin for crossword game state.

Currently tracks just enough per-game state to notify players when a
bot restart interrupts their game. A future iteration can extend this
with a full game snapshot for true resume-across-restart.
"""
from db import DatabaseMixin


class CrosswordMixin(DatabaseMixin):
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
    ) -> None:
        """Record a newly started crossword game.

        Upserts on ``channel_id`` so a stale row from a previous run is
        replaced rather than raising a conflict.
        """
        await self._execute(
            '''
            INSERT INTO crossword_active_games
                (channel_id, starter_id, guild_id, is_dm, message_id,
                 language, difficulty, total_words, solved_count,
                 started_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, NOW(), NOW())
            ON CONFLICT (channel_id) DO UPDATE
            SET starter_id   = EXCLUDED.starter_id,
                guild_id     = EXCLUDED.guild_id,
                is_dm        = EXCLUDED.is_dm,
                message_id   = EXCLUDED.message_id,
                language     = EXCLUDED.language,
                difficulty   = EXCLUDED.difficulty,
                total_words  = EXCLUDED.total_words,
                solved_count = 0,
                started_at   = NOW(),
                updated_at   = NOW()
            ''',
            channel_id, starter_id, guild_id, is_dm, message_id,
            language, difficulty, total_words,
        )

    async def crossword_bump_solved(self, channel_id: int) -> None:
        """Increment ``solved_count`` for an active game. No-op if missing."""
        await self._execute(
            '''
            UPDATE crossword_active_games
            SET solved_count = solved_count + 1,
                updated_at = NOW()
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
