
from db import DatabaseMixin

class NotesMixin(DatabaseMixin):
    async def add_note(self, user_id: int, username: str, content: str) -> int:
        """Add a new note to the database"""
        row = await self._fetchrow(
            'INSERT INTO notes (user_id, username, content) VALUES ($1, $2, $3) RETURNING id',
            user_id, username, content,
        )
        return row['id']

    async def get_note(self, note_id: int) -> dict | None:
        """Get a note by its ID"""
        row = await self._fetchrow(
            'SELECT id, user_id, username, content, created_at FROM notes WHERE id = $1',
            note_id,
        )
        return dict(row) if row else None

    async def get_user_notes(self, user_id: int, limit: int = 10) -> list[dict]:
        """Get all notes for a specific user"""
        rows = await self._fetch(
            'SELECT id, user_id, username, content, created_at FROM notes WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2',
            user_id, limit,
        )
        return [dict(row) for row in rows]

    async def delete_note(self, note_id: int, user_id: int) -> bool:
        """Delete a note (only if it belongs to the user)"""
        result = await self._execute(
            'DELETE FROM notes WHERE id = $1 AND user_id = $2',
            note_id, user_id,
        )
        return result == 'DELETE 1'
