from typing import Optional
import logging
from db import DatabaseMixin

logger = logging.getLogger(__name__)


class IntroductionsMixin(DatabaseMixin):
    async def check_user_introduction(self, user_id: int) -> Optional[dict]:
        """Check if user has posted an introduction in the last 90 days"""
        row = await self._fetchrow('''
            SELECT id, user_id, posted_at
            FROM introductions
            WHERE user_id = $1
            AND posted_at > NOW() - INTERVAL '90 days'
            ORDER BY posted_at DESC
            LIMIT 1
        ''', user_id)
        return dict(row) if row else None

    async def get_introduction_count(self, user_id: int) -> int:
        """Get total number of introductions a user has posted"""
        count = await self._fetchval(
            'SELECT COUNT(*) FROM introductions WHERE user_id = $1', user_id,
        )
        return count or 0

    async def record_introduction(self, user_id: int) -> bool:
        """Record a user's introduction attempt"""
        try:
            await self._execute(
                'INSERT INTO introductions (user_id, posted_at) VALUES ($1, NOW())', user_id,
            )
            return True
        except Exception as e:
            logger.error(f"Error recording introduction: {e}")
            return False
