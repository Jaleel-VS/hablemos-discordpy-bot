from typing import Optional
from db import DatabaseMixin


class VocabMixin(DatabaseMixin):
    async def add_vocab_note(self, user_id: int, username: str, word: str,
                            translation: Optional[str] = None,
                            language: Optional[str] = None) -> int:
        """Add a new vocabulary note to the database"""
        row = await self._fetchrow('''
            INSERT INTO vocab_notes (user_id, username, word, translation, language)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
        ''', user_id, username, word, translation, language)
        return row['id']

    async def get_user_vocab_notes(self, user_id: int, limit: int = 50) -> list[dict]:
        """Get all vocab notes for a specific user"""
        rows = await self._fetch('''
            SELECT id, user_id, username, word, translation, language, created_at
            FROM vocab_notes WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2
        ''', user_id, limit)
        return [dict(row) for row in rows]

    async def search_vocab_notes(self, user_id: int, search_term: str,
                                 limit: int = 20) -> list[dict]:
        """Search vocab notes by word or translation"""
        search_pattern = f'%{search_term}%'
        rows = await self._fetch('''
            SELECT id, user_id, username, word, translation, language, created_at
            FROM vocab_notes
            WHERE user_id = $1 AND (word ILIKE $2 OR translation ILIKE $2)
            ORDER BY created_at DESC LIMIT $3
        ''', user_id, search_pattern, limit)
        return [dict(row) for row in rows]

    async def delete_vocab_note(self, note_id: int, user_id: int) -> bool:
        """Delete a vocab note (only if it belongs to the user)"""
        result = await self._execute(
            'DELETE FROM vocab_notes WHERE id = $1 AND user_id = $2', note_id, user_id,
        )
        return result == 'DELETE 1'

    async def get_vocab_note_count(self, user_id: int) -> int:
        """Get total count of vocab notes for a user"""
        count = await self._fetchval(
            'SELECT COUNT(*) FROM vocab_notes WHERE user_id = $1', user_id,
        )
        return count or 0
