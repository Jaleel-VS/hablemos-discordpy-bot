import logging
from datetime import UTC

from db import DatabaseMixin

logger = logging.getLogger(__name__)

class PracticeMixin(DatabaseMixin):
    async def add_practice_card(self, word: str, translation: str, language: str,
                                sentence: str, sentence_with_blank: str) -> int | None:
        """Add a practice card to the global card pool. Returns card ID or None if duplicate."""
        try:
            row = await self._fetchrow('''
                INSERT INTO practice_cards (word, translation, language, sentence, sentence_with_blank)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (word, language) DO NOTHING
                RETURNING id
            ''', word, translation, language, sentence, sentence_with_blank)
            return row['id'] if row else None
        except Exception as e:
            logger.error("Error adding practice card: %s", e)
            return None

    async def get_cards_for_language(self, language: str) -> list[dict]:
        """Get all practice cards for a language"""
        rows = await self._fetch('''
            SELECT id, word, translation, language, sentence, sentence_with_blank, created_at
            FROM practice_cards WHERE language = $1 ORDER BY id
        ''', language)
        return [dict(row) for row in rows]

    async def get_due_cards(self, user_id: int, language: str, limit: int = 10) -> list[dict]:
        """Get cards due for review for a user."""
        rows = await self._fetch('''
            SELECT pc.id, pc.word, pc.translation, pc.language,
                   pc.sentence, pc.sentence_with_blank,
                   ucp.interval_days, ucp.ease_factor, ucp.repetitions,
                   ucp.last_review, ucp.next_review
            FROM practice_cards pc
            JOIN user_card_progress ucp ON pc.id = ucp.card_id
            WHERE ucp.user_id = $1 AND pc.language = $2 AND ucp.next_review <= NOW()
            ORDER BY ucp.next_review ASC LIMIT $3
        ''', user_id, language, limit)
        return [dict(row) for row in rows]

    async def get_new_cards(self, user_id: int, language: str, limit: int = 10) -> list[dict]:
        """Get cards the user hasn't seen yet."""
        rows = await self._fetch('''
            SELECT pc.id, pc.word, pc.translation, pc.language,
                   pc.sentence, pc.sentence_with_blank
            FROM practice_cards pc
            WHERE pc.language = $1
              AND pc.id NOT IN (SELECT card_id FROM user_card_progress WHERE user_id = $2)
            ORDER BY pc.id LIMIT $3
        ''', language, user_id, limit)
        return [dict(row) for row in rows]

    async def update_user_progress(self, user_id: int, card_id: int,
                                   interval_days: float, ease_factor: float,
                                   repetitions: int, next_review) -> None:
        """Update or create user progress for a card."""
        await self._execute('''
            INSERT INTO user_card_progress
                (user_id, card_id, interval_days, ease_factor, repetitions, last_review, next_review)
            VALUES ($1, $2, $3, $4, $5, NOW(), $6)
            ON CONFLICT (user_id, card_id) DO UPDATE
            SET interval_days = $3, ease_factor = $4, repetitions = $5,
                last_review = NOW(), next_review = $6
        ''', user_id, card_id, interval_days, ease_factor, repetitions, next_review)

    async def get_card_distractors(self, language: str, exclude_word: str, count: int = 3) -> list[str]:
        """Get random words for multiple choice distractors."""
        rows = await self._fetch('''
            SELECT word FROM practice_cards
            WHERE language = $1 AND word != $2
            ORDER BY RANDOM() LIMIT $3
        ''', language, exclude_word, count)
        return [row['word'] for row in rows]

    async def get_practice_stats(self, user_id: int, language: str) -> dict:
        """Get practice statistics for a user."""
        total = await self._fetchval(
            'SELECT COUNT(*) FROM practice_cards WHERE language = $1', language,
        )
        user_cards = await self._fetch('''
            SELECT ucp.interval_days, ucp.next_review, ucp.repetitions
            FROM user_card_progress ucp
            JOIN practice_cards pc ON ucp.card_id = pc.id
            WHERE ucp.user_id = $1 AND pc.language = $2
        ''', user_id, language)

        new_count = (total or 0) - len(user_cards)
        due_count = learning_count = mastered_count = 0

        from datetime import datetime
        now = datetime.now(UTC)
        for card in user_cards:
            if card['next_review'] and card['next_review'] <= now:
                due_count += 1
            elif card['interval_days'] >= 21:
                mastered_count += 1
            else:
                learning_count += 1

        return {
            'total': total or 0, 'new': new_count,
            'learning': learning_count, 'due': due_count, 'mastered': mastered_count,
        }

    async def get_practice_card_count(self, language: str) -> int:
        """Get total count of practice cards for a language"""
        count = await self._fetchval(
            'SELECT COUNT(*) FROM practice_cards WHERE language = $1', language,
        )
        return count or 0
