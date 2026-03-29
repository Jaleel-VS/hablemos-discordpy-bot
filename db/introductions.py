
import logging

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class IntroductionsMixin(DatabaseMixin):
    async def check_user_introduction(self, user_id: int, cooldown_days: int = 90) -> dict | None:
        """Check if user has posted an introduction within the cooldown window."""
        row = await self._fetchrow('''
            SELECT id, user_id, posted_at
            FROM introductions
            WHERE user_id = $1
            AND posted_at > NOW() - make_interval(days => $2)
            ORDER BY posted_at DESC
            LIMIT 1
        ''', user_id, cooldown_days)
        return dict(row) if row else None

    async def get_introduction_count(self, user_id: int) -> int:
        """Get total number of introductions a user has posted."""
        count = await self._fetchval(
            'SELECT COUNT(*) FROM introductions WHERE user_id = $1', user_id,
        )
        return count or 0

    async def clear_introductions(self, user_id: int) -> str:
        """Delete all introduction records for a user. Returns status string."""
        return await self._execute(
            'DELETE FROM introductions WHERE user_id = $1', user_id,
        )

    async def record_introduction(self, user_id: int) -> bool:
        """Record a user's introduction attempt."""
        try:
            await self._execute(
                'INSERT INTO introductions (user_id, posted_at) VALUES ($1, NOW())', user_id,
            )
            return True
        except Exception as e:
            logger.error("Error recording introduction: %s", e)
            return False

    async def get_introduction_stats(self, cooldown_days: int = 90) -> dict:
        """Get introduction tracker statistics."""
        rows = await self._fetch('''
            SELECT
                COUNT(*) AS total,
                COUNT(DISTINCT user_id) AS unique_users,
                COUNT(*) FILTER (
                    WHERE posted_at > NOW() - make_interval(days => $1)
                ) AS recent
            FROM introductions
        ''', cooldown_days)
        row = rows[0]
        return {"total": row["total"], "unique_users": row["unique_users"], "recent": row["recent"]}

    # ── Intro exemptions ──

    async def get_intro_exempt_users(self) -> set[int]:
        """Return set of user IDs exempt from intro tracking."""
        rows = await self._fetch('SELECT user_id FROM intro_exempt_users')
        return {row['user_id'] for row in rows}

    async def add_intro_exempt_user(self, user_id: int, added_by: int) -> bool:
        """Add a user to the intro exemption list. Returns False if already exempt."""
        result = await self._execute('''
            INSERT INTO intro_exempt_users (user_id, added_by)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING
        ''', user_id, added_by)
        return result.endswith('1')

    async def remove_intro_exempt_user(self, user_id: int) -> bool:
        """Remove a user from the intro exemption list. Returns False if not found."""
        result = await self._execute(
            'DELETE FROM intro_exempt_users WHERE user_id = $1', user_id,
        )
        return result.endswith('1')
