"""Database mixin for channel interaction tracking."""
from datetime import datetime

from db import DatabaseMixin


class InteractionsMixin(DatabaseMixin):

    async def record_interaction(
        self,
        channel_id: int,
        guild_id: int,
        user_a: int,
        user_b: int,
        interaction_type: str,
    ) -> None:
        """Record a reply or mention interaction between two users."""
        # Normalize pair so (A,B) and (B,A) are the same row
        lo, hi = min(user_a, user_b), max(user_a, user_b)
        await self._execute(
            """
            INSERT INTO interactions (channel_id, guild_id, user_a, user_b, interaction_type)
            VALUES ($1, $2, $3, $4, $5)
            """,
            channel_id, guild_id, lo, hi, interaction_type,
        )

    async def get_top_pairs(
        self,
        channel_id: int,
        after: datetime,
        limit: int = 10,
    ) -> list[dict]:
        """Return top interaction pairs with reply/mention counts and a weighted score."""
        rows = await self._fetch(
            """
            SELECT user_a, user_b,
                   COUNT(*) FILTER (WHERE interaction_type = 'reply')  AS replies,
                   COUNT(*) FILTER (WHERE interaction_type = 'mention') AS mentions,
                   COUNT(*) FILTER (WHERE interaction_type = 'reply') * 2
                     + COUNT(*) FILTER (WHERE interaction_type = 'mention') AS score
            FROM interactions
            WHERE channel_id = $1 AND created_at >= $2
            GROUP BY user_a, user_b
            ORDER BY score DESC
            LIMIT $3
            """,
            channel_id, after, limit,
        )
        return [dict(r) for r in rows]

    async def get_interaction_stats(
        self,
        channel_id: int,
        after: datetime,
    ) -> dict:
        """Return aggregate interaction stats for a channel."""
        row = await self._fetchrow(
            """
            SELECT
                COUNT(DISTINCT (user_a, user_b)) AS unique_pairs,
                COUNT(*) FILTER (WHERE interaction_type = 'reply')  AS total_replies,
                COUNT(*) FILTER (WHERE interaction_type = 'mention') AS total_mentions
            FROM interactions
            WHERE channel_id = $1 AND created_at >= $2
            """,
            channel_id, after,
        )
        return dict(row) if row else {"unique_pairs": 0, "total_replies": 0, "total_mentions": 0}

    async def purge_old_interactions(self, days: int) -> int:
        """Delete interaction rows older than N days. Returns rows deleted."""
        result = await self._execute(
            "DELETE FROM interactions WHERE created_at < NOW() - INTERVAL '1 day' * $1",
            days,
        )
        # result is like 'DELETE 42'
        return int(result.split()[-1])
