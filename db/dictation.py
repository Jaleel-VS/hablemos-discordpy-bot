"""Database mixin for dictation sentences and scores."""

import logging

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class DictationMixin(DatabaseMixin):
    """Query helpers for dictation_sentences and dictation_scores."""

    async def get_random_dictation(
        self, language: str, level: str, user_id: int | None = None,
    ) -> dict | None:
        """Return a random sentence, preferring unattempted ones for the user."""
        if user_id:
            # Prefer sentences the user hasn't tried yet
            row = await self._fetchrow("""
                SELECT s.id, s.language, s.level, s.sentence, s.audio_url
                FROM dictation_sentences s
                LEFT JOIN dictation_scores sc
                    ON sc.sentence_id = s.id AND sc.user_id = $3
                WHERE s.language = $1 AND s.level = $2 AND s.audio_url IS NOT NULL
                    AND sc.id IS NULL
                ORDER BY random() LIMIT 1
            """, language, level, user_id)
            if row:
                return dict(row)

        # Fallback: any sentence with audio
        row = await self._fetchrow("""
            SELECT id, language, level, sentence, audio_url
            FROM dictation_sentences
            WHERE language = $1 AND level = $2 AND audio_url IS NOT NULL
            ORDER BY random() LIMIT 1
        """, language, level)
        return dict(row) if row else None

    async def record_dictation_score(
        self, user_id: int, sentence_id: int, score: int, user_answer: str,
    ) -> None:
        """Record a user's dictation attempt."""
        await self._execute("""
            INSERT INTO dictation_scores (user_id, sentence_id, score, user_answer)
            VALUES ($1, $2, $3, $4)
        """, user_id, sentence_id, score, user_answer)

    async def get_dictation_stats(self, user_id: int) -> dict:
        """Return aggregate stats for a user's dictation attempts."""
        row = await self._fetchrow("""
            SELECT count(*) AS total,
                   coalesce(avg(score), 0) AS avg_score,
                   count(*) FILTER (WHERE score = 4) AS perfect
            FROM dictation_scores WHERE user_id = $1
        """, user_id)
        return dict(row) if row else {"total": 0, "avg_score": 0, "perfect": 0}
