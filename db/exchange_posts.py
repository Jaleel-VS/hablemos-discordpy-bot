"""Database mixin for exchange partner post tracking."""
import logging
from datetime import datetime

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class ExchangePostsMixin(DatabaseMixin):
    """Queries for the exchange_posts table."""

    async def save_exchange_post(
        self,
        user_id: int,
        message_id: int,
        channel_id: int,
    ) -> bool:
        """Save or replace a user's exchange post reference."""
        try:
            await self._execute(
                """INSERT INTO exchange_posts (user_id, message_id, channel_id)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (user_id)
                   DO UPDATE SET message_id = $2, channel_id = $3, posted_at = NOW()""",
                user_id, message_id, channel_id,
            )
            return True
        except Exception:
            logger.exception("Failed to save exchange post for user %s", user_id)
            return False

    async def get_exchange_post(self, user_id: int) -> dict | None:
        """Get a user's current exchange post."""
        row = await self._fetchrow(
            "SELECT user_id, message_id, channel_id, posted_at FROM exchange_posts WHERE user_id = $1",
            user_id,
        )
        return dict(row) if row else None

    async def delete_exchange_post(self, user_id: int) -> bool:
        """Delete a user's exchange post record."""
        result = await self._execute(
            "DELETE FROM exchange_posts WHERE user_id = $1", user_id,
        )
        return result.endswith("1")

    async def get_exchange_post_by_message(self, message_id: int) -> dict | None:
        """Look up an exchange post by its Discord message ID."""
        row = await self._fetchrow(
            "SELECT user_id, message_id, channel_id, posted_at FROM exchange_posts WHERE message_id = $1",
            message_id,
        )
        return dict(row) if row else None

    async def can_repost_exchange(self, user_id: int, cooldown_days: int = 14, grace_minutes: int = 10) -> tuple[bool, datetime | None]:
        """Check if a user can repost. Allowed within grace_minutes or after cooldown_days."""
        row = await self._fetchrow(
            "SELECT posted_at FROM exchange_posts WHERE user_id = $1", user_id,
        )
        if not row:
            return True, None
        posted_at = row["posted_at"]
        # Allow repost within grace period OR after full cooldown
        can = await self._fetchval(
            """SELECT $1 > NOW() - make_interval(mins => $2)
                   OR $1 < NOW() - make_interval(days => $3)""",
            posted_at, grace_minutes, cooldown_days,
        )
        return can, posted_at
