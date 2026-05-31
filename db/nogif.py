"""Database mixin for no-GIF restrictions."""
from datetime import datetime

from db import DatabaseMixin


class NoGifMixin(DatabaseMixin):
    """Queries for the ``nogif_restrictions`` table."""

    async def upsert_nogif_restriction(
        self,
        user_id: int,
        guild_id: int,
        expires_at: datetime,
    ) -> None:
        """Insert or update a no-GIF restriction for a user."""
        await self._execute(
            '''
            INSERT INTO nogif_restrictions (user_id, guild_id, expires_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, guild_id) DO UPDATE
            SET expires_at = EXCLUDED.expires_at
            ''',
            user_id, guild_id, expires_at,
        )

    async def delete_nogif_restriction(self, user_id: int, guild_id: int) -> None:
        """Remove a restriction (called on expiry or manual lift)."""
        await self._execute(
            'DELETE FROM nogif_restrictions WHERE user_id = $1 AND guild_id = $2',
            user_id, guild_id,
        )

    async def get_active_nogif_restrictions(self) -> list:
        """Return all unexpired restrictions across all guilds."""
        return await self._fetch(
            '''
            SELECT user_id, guild_id, expires_at
            FROM nogif_restrictions
            WHERE expires_at > NOW()
            ORDER BY expires_at ASC
            ''',
        )

    async def get_nogif_restriction(self, user_id: int, guild_id: int):
        """Return the restriction row for a specific user, or None."""
        return await self._fetchrow(
            '''
            SELECT user_id, guild_id, expires_at
            FROM nogif_restrictions
            WHERE user_id = $1 AND guild_id = $2
            ''',
            user_id, guild_id,
        )
