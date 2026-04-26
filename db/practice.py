"""Database mixin for SRS practice cards and user progress."""
import logging
from datetime import UTC, datetime

from fsrs import Card

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class PracticeMixin(DatabaseMixin):
    async def add_practice_card(self, word: str, translation: str, language: str,
                                sentence: str, sentence_with_blank: str,
                                sentence_translation: str = "", level: str = "") -> int | None:
        """Add a practice card to the global card pool. Returns card ID or None if duplicate."""
        try:
            row = await self._fetchrow('''
                INSERT INTO practice_cards (word, translation, language, sentence,
                    sentence_with_blank, sentence_translation, level)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (word, language) DO NOTHING
                RETURNING id
            ''', word, translation, language, sentence, sentence_with_blank,
                sentence_translation, level)
            return row['id'] if row else None
        except Exception as e:
            logger.error("Error adding practice card: %s", e)
            return None

    async def get_cards_for_language(self, language: str) -> list[dict]:
        """Get all practice cards for a language."""
        rows = await self._fetch('''
            SELECT id, word, translation, language, sentence, sentence_with_blank,
                   sentence_translation, level, created_at
            FROM practice_cards WHERE language = $1 ORDER BY id
        ''', language)
        return [dict(row) for row in rows]

    async def get_due_cards(self, user_id: int, language: str, limit: int = 10,
                            level: str | None = None) -> list[dict]:
        """Get cards due for review for a user, optionally filtered by level."""
        if level:
            rows = await self._fetch('''
                SELECT pc.id, pc.word, pc.translation, pc.language,
                       pc.sentence, pc.sentence_with_blank,
                       pc.sentence_translation, pc.level,
                       ucp.card_json
                FROM practice_cards pc
                JOIN user_card_progress ucp ON pc.id = ucp.card_id
                WHERE ucp.user_id = $1 AND pc.language = $2 AND pc.level = $3
                      AND ucp.next_review <= NOW()
                ORDER BY ucp.next_review ASC LIMIT $4
            ''', user_id, language, level, limit)
        else:
            rows = await self._fetch('''
                SELECT pc.id, pc.word, pc.translation, pc.language,
                       pc.sentence, pc.sentence_with_blank,
                       pc.sentence_translation, pc.level,
                       ucp.card_json
                FROM practice_cards pc
                JOIN user_card_progress ucp ON pc.id = ucp.card_id
                WHERE ucp.user_id = $1 AND pc.language = $2
                      AND ucp.next_review <= NOW()
                ORDER BY ucp.next_review ASC LIMIT $3
            ''', user_id, language, limit)
        return [dict(row) for row in rows]

    async def get_new_cards(self, user_id: int, language: str, limit: int = 10,
                            level: str | None = None) -> list[dict]:
        """Get cards the user hasn't seen yet, optionally filtered by level."""
        if level:
            rows = await self._fetch('''
                SELECT pc.id, pc.word, pc.translation, pc.language,
                       pc.sentence, pc.sentence_with_blank,
                       pc.sentence_translation, pc.level
                FROM practice_cards pc
                WHERE pc.language = $1 AND pc.level = $2
                  AND pc.id NOT IN (SELECT card_id FROM user_card_progress WHERE user_id = $3)
                ORDER BY RANDOM() LIMIT $4
            ''', language, level, user_id, limit)
        else:
            rows = await self._fetch('''
                SELECT pc.id, pc.word, pc.translation, pc.language,
                       pc.sentence, pc.sentence_with_blank,
                       pc.sentence_translation, pc.level
                FROM practice_cards pc
                WHERE pc.language = $1
                  AND pc.id NOT IN (SELECT card_id FROM user_card_progress WHERE user_id = $2)
                ORDER BY RANDOM() LIMIT $3
            ''', language, user_id, limit)
        return [dict(row) for row in rows]

    async def update_user_progress(self, user_id: int, card_id: int,
                                   card_json: str, next_review: str) -> None:
        """Update or create user progress for a card using FSRS state."""
        await self._execute('''
            INSERT INTO user_card_progress (user_id, card_id, card_json, next_review)
            VALUES ($1, $2, $3, $4::timestamptz)
            ON CONFLICT (user_id, card_id) DO UPDATE
            SET card_json = $3, next_review = $4::timestamptz
        ''', user_id, card_id, card_json, next_review)

    async def get_card_distractors(self, language: str, exclude_word: str,
                                   count: int = 3, level: str | None = None) -> list[str]:
        """Get random words for multiple choice distractors, optionally from same level."""
        if level:
            rows = await self._fetch('''
                SELECT word FROM practice_cards
                WHERE language = $1 AND word != $2 AND level = $3
                ORDER BY RANDOM() LIMIT $4
            ''', language, exclude_word, level, count)
        else:
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
            SELECT ucp.card_json, ucp.next_review
            FROM user_card_progress ucp
            JOIN practice_cards pc ON ucp.card_id = pc.id
            WHERE ucp.user_id = $1 AND pc.language = $2
        ''', user_id, language)

        new_count = (total or 0) - len(user_cards)
        due_count = learning_count = mastered_count = 0

        now = datetime.now(UTC)
        for row in user_cards:
            if row['next_review'] and row['next_review'] <= now:
                due_count += 1
            elif row['card_json']:
                card = Card.from_json(row['card_json'])
                if card.state == 2 and card.stability >= 21:
                    mastered_count += 1
                else:
                    learning_count += 1
            else:
                learning_count += 1

        return {
            'total': total or 0, 'new': new_count,
            'learning': learning_count, 'due': due_count, 'mastered': mastered_count,
        }

    async def get_practice_card_count(self, language: str) -> int:
        """Get total count of practice cards for a language."""
        count = await self._fetchval(
            'SELECT COUNT(*) FROM practice_cards WHERE language = $1', language,
        )
        return count or 0

    async def get_random_cards(self, language: str, limit: int = 10,
                               level: str | None = None) -> list[dict]:
        """Get random cards for untracked practice."""
        if level:
            rows = await self._fetch('''
                SELECT id, word, translation, language, sentence,
                       sentence_with_blank, sentence_translation, level
                FROM practice_cards
                WHERE language = $1 AND level = $2
                ORDER BY RANDOM() LIMIT $3
            ''', language, level, limit)
        else:
            rows = await self._fetch('''
                SELECT id, word, translation, language, sentence,
                       sentence_with_blank, sentence_translation, level
                FROM practice_cards WHERE language = $1
                ORDER BY RANDOM() LIMIT $2
            ''', language, limit)
        return [dict(row) for row in rows]
