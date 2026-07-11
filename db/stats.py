"""Stats database mixin — channel activity and user adoption tracking."""
import logging
from datetime import UTC, datetime

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class StatsMixin(DatabaseMixin):
    """Query methods for stats tracking (channel_stats + user_activity)."""

    # ── Upserts (called from on_message listener) ──

    async def upsert_channel_stat(
        self, channel_id: int, role_type: str, hour_bucket: datetime
    ) -> None:
        """Increment message count for a channel/role/hour bucket."""
        await self._execute(
            """
            INSERT INTO channel_stats (channel_id, role_type, hour_bucket, msg_count)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (channel_id, role_type, hour_bucket)
            DO UPDATE SET msg_count = channel_stats.msg_count + 1
            """,
            channel_id,
            role_type,
            hour_bucket,
        )

    async def upsert_user_activity(self, user_id: int, role_type: str) -> None:
        """Record user activity (first_seen on insert, last_seen on update)."""
        now = datetime.now(UTC)
        await self._execute(
            """
            INSERT INTO user_activity (user_id, role_type, first_seen, last_seen)
            VALUES ($1, $2, $3, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET role_type = $2, last_seen = $3
            """,
            user_id,
            role_type,
            now,
        )

    async def track_message_stats(
        self,
        channel_id: int,
        user_id: int,
        role_type: str,
        hour_bucket: datetime,
    ) -> None:
        """Record all per-message stats updates atomically."""
        now = datetime.now(UTC)
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute(
                """
                    INSERT INTO channel_stats (
                        channel_id, role_type, hour_bucket, msg_count
                    )
                    VALUES ($1, $2, $3, 1)
                    ON CONFLICT (channel_id, role_type, hour_bucket)
                    DO UPDATE SET msg_count = channel_stats.msg_count + 1
                    """,
                channel_id,
                role_type,
                hour_bucket,
            )
            await conn.execute(
                """
                    INSERT INTO user_activity (
                        user_id, role_type, first_seen, last_seen
                    )
                    VALUES ($1, $2, $3, $3)
                    ON CONFLICT (user_id)
                    DO UPDATE SET role_type = $2, last_seen = $3
                    """,
                user_id,
                role_type,
                now,
            )
            await conn.execute(
                """
                    INSERT INTO user_message_counts (
                        user_id, hour_bucket, msg_count
                    )
                    VALUES ($1, $2, 1)
                    ON CONFLICT (user_id, hour_bucket)
                    DO UPDATE SET msg_count = user_message_counts.msg_count + 1
                    """,
                user_id,
                hour_bucket,
            )

    # ── Channel stats queries ──

    async def upsert_user_message_count(
        self, user_id: int, hour_bucket: datetime
    ) -> None:
        """Increment message count for a user/hour bucket."""
        await self._execute(
            """
            INSERT INTO user_message_counts (user_id, hour_bucket, msg_count)
            VALUES ($1, $2, 1)
            ON CONFLICT (user_id, hour_bucket)
            DO UPDATE SET msg_count = user_message_counts.msg_count + 1
            """,
            user_id,
            hour_bucket,
        )

    async def get_top_channels(
        self, days: int = 7, limit: int = 10
    ) -> list[dict]:
        """Top channels by total message count in the last N days."""
        rows = await self._fetch(
            """
            SELECT channel_id, SUM(msg_count) AS total
            FROM channel_stats
            WHERE hour_bucket >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY channel_id
            ORDER BY total DESC
            LIMIT $2
            """,
            str(days),
            limit,
        )
        return [dict(r) for r in rows]

    async def get_top_users(
        self, days: int = 7, limit: int = 10
    ) -> list[dict]:
        """Top users by total message count in the last N days."""
        rows = await self._fetch(
            """
            SELECT
                user_id,
                SUM(msg_count) AS total,
                COUNT(DISTINCT (hour_bucket AT TIME ZONE 'UTC')::DATE) AS active_days
            FROM user_message_counts
            WHERE hour_bucket >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY user_id
            ORDER BY total DESC
            LIMIT $2
            """,
            str(days),
            limit,
        )
        return [dict(r) for r in rows]

    async def get_activity_totals_between(
        self, start_at: datetime, end_at: datetime
    ) -> dict:
        """Return message, active-user, and new-user totals for a period."""
        row = await self._fetchrow(
            """
            SELECT
                COALESCE((
                    SELECT SUM(msg_count)
                    FROM channel_stats
                    WHERE hour_bucket >= $1 AND hour_bucket < $2
                ), 0) AS total_messages,
                (
                    SELECT COUNT(DISTINCT user_id)
                    FROM user_message_counts
                    WHERE hour_bucket >= $1 AND hour_bucket < $2
                ) AS active_users,
                (
                    SELECT COUNT(*)
                    FROM user_activity
                    WHERE first_seen >= $1 AND first_seen < $2
                ) AS new_users
            """,
            start_at,
            end_at,
        )
        if row is None:
            return {"total_messages": 0, "active_users": 0, "new_users": 0}
        return dict(row)

    async def get_channel_period_deltas(
        self,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> list[dict]:
        """Return per-channel message deltas between two equal periods."""
        rows = await self._fetch(
            """
            WITH current_period AS (
                SELECT channel_id, SUM(msg_count) AS total
                FROM channel_stats
                WHERE hour_bucket >= $1 AND hour_bucket < $2
                GROUP BY channel_id
            ),
            previous_period AS (
                SELECT channel_id, SUM(msg_count) AS total
                FROM channel_stats
                WHERE hour_bucket >= $3 AND hour_bucket < $4
                GROUP BY channel_id
            )
            SELECT
                COALESCE(c.channel_id, p.channel_id) AS channel_id,
                COALESCE(c.total, 0) AS current_total,
                COALESCE(p.total, 0) AS previous_total,
                COALESCE(c.total, 0) - COALESCE(p.total, 0) AS delta
            FROM current_period c
            FULL OUTER JOIN previous_period p USING (channel_id)
            WHERE COALESCE(c.total, 0) <> COALESCE(p.total, 0)
            ORDER BY ABS(COALESCE(c.total, 0) - COALESCE(p.total, 0)) DESC
            """,
            current_start,
            current_end,
            previous_start,
            previous_end,
        )
        return [dict(r) for r in rows]

    async def get_role_period_deltas(
        self,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> list[dict]:
        """Return native-role message deltas between two equal periods."""
        rows = await self._fetch(
            """
            WITH current_period AS (
                SELECT role_type, SUM(msg_count) AS total
                FROM channel_stats
                WHERE hour_bucket >= $1 AND hour_bucket < $2
                GROUP BY role_type
            ),
            previous_period AS (
                SELECT role_type, SUM(msg_count) AS total
                FROM channel_stats
                WHERE hour_bucket >= $3 AND hour_bucket < $4
                GROUP BY role_type
            )
            SELECT
                COALESCE(c.role_type, p.role_type) AS role_type,
                COALESCE(c.total, 0) AS current_total,
                COALESCE(p.total, 0) AS previous_total,
                COALESCE(c.total, 0) - COALESCE(p.total, 0) AS delta
            FROM current_period c
            FULL OUTER JOIN previous_period p USING (role_type)
            ORDER BY current_total DESC, role_type
            """,
            current_start,
            current_end,
            previous_start,
            previous_end,
        )
        return [dict(r) for r in rows]

    async def get_peak_activity_window(
        self, start_at: datetime, end_at: datetime
    ) -> dict:
        """Return the busiest day-of-week/hour bucket in a period."""
        row = await self._fetchrow(
            """
            SELECT
                EXTRACT(DOW FROM hour_bucket AT TIME ZONE 'UTC') AS dow,
                EXTRACT(HOUR FROM hour_bucket AT TIME ZONE 'UTC') AS hour,
                SUM(msg_count) AS total
            FROM channel_stats
            WHERE hour_bucket >= $1 AND hour_bucket < $2
            GROUP BY dow, hour
            ORDER BY total DESC
            LIMIT 1
            """,
            start_at,
            end_at,
        )
        if row is None:
            return {"dow": None, "hour": None, "total": 0}
        return dict(row)

    async def get_role_breakdown(self, days: int = 7) -> list[dict]:
        """Message counts grouped by role_type in the last N days."""
        rows = await self._fetch(
            """
            SELECT role_type, SUM(msg_count) AS total
            FROM channel_stats
            WHERE hour_bucket >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY role_type
            ORDER BY total DESC
            """,
            str(days),
        )
        return [dict(r) for r in rows]

    async def get_daily_activity(self, days: int = 7) -> list[dict]:
        """Daily message counts by role_type for the last N days."""
        rows = await self._fetch(
            """
            SELECT
                date_trunc('day', hour_bucket AT TIME ZONE 'UTC') AS day,
                role_type,
                SUM(msg_count) AS total
            FROM channel_stats
            WHERE hour_bucket >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY day, role_type
            ORDER BY day
            """,
            str(days),
        )
        return [dict(r) for r in rows]

    async def get_hourly_heatmap(self, days: int = 7) -> list[dict]:
        """Message counts by hour-of-day and day-of-week for heatmap."""
        rows = await self._fetch(
            """
            SELECT
                EXTRACT(DOW FROM hour_bucket AT TIME ZONE 'UTC') AS dow,
                EXTRACT(HOUR FROM hour_bucket AT TIME ZONE 'UTC') AS hour,
                SUM(msg_count) AS total
            FROM channel_stats
            WHERE hour_bucket >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY dow, hour
            ORDER BY dow, hour
            """,
            str(days),
        )
        return [dict(r) for r in rows]

    # ── User adoption queries ──

    async def get_new_users_per_week(self, weeks: int = 8) -> list[dict]:
        """Count of new users per week (by first_seen)."""
        rows = await self._fetch(
            """
            SELECT
                date_trunc('week', first_seen) AS week,
                COUNT(*) AS new_users
            FROM user_activity
            WHERE first_seen >= NOW() - ($1 || ' weeks')::INTERVAL
            GROUP BY week
            ORDER BY week
            """,
            str(weeks),
        )
        return [dict(r) for r in rows]

    async def get_active_users_count(self, days: int = 30) -> int:
        """Count of users active in the last N days."""
        val = await self._fetchval(
            """
            SELECT COUNT(*)
            FROM user_activity
            WHERE last_seen >= NOW() - ($1 || ' days')::INTERVAL
            """,
            str(days),
        )
        return val or 0

    async def get_total_users(self) -> int:
        """Total unique users ever tracked."""
        val = await self._fetchval("SELECT COUNT(*) FROM user_activity")
        return val or 0

    async def get_growth_summary(self, new_user_days: int = 30) -> dict:
        """Summary: total users, 30-day MAU, and new users this period."""
        total = await self.get_total_users()
        mau = await self.get_active_users_count(30)
        new_users = await self._fetchval(
            """
            SELECT COUNT(*)
            FROM user_activity
            WHERE first_seen >= NOW() - ($1 || ' days')::INTERVAL
            """,
            str(new_user_days),
        )
        return {
            "total_users": total,
            "monthly_active": mau,
            "new_users": new_users or 0,
        }
