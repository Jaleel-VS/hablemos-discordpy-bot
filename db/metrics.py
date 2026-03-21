"""Database mixin for command metrics and cog management."""
import logging

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class MetricsMixin(DatabaseMixin):
    """Queries for command usage metrics and cog toggle state."""

    # ── Cog settings ──

    async def get_disabled_cogs(self) -> set[str]:
        """Return set of cog extension names that are disabled."""
        rows = await self._fetch(
            "SELECT cog_name FROM cog_settings WHERE enabled = FALSE"
        )
        return {r['cog_name'] for r in rows}

    async def set_cog_enabled(self, cog_name: str, enabled: bool) -> None:
        """Enable or disable a cog by extension name."""
        await self._execute('''
            INSERT INTO cog_settings (cog_name, enabled)
            VALUES ($1, $2)
            ON CONFLICT (cog_name) DO UPDATE SET enabled = $2
        ''', cog_name, enabled)

    # ── Command metrics ──

    async def record_command(self, command_name: str, cog_name: str | None,
                             user_id: int, guild_id: int | None,
                             channel_id: int | None, is_slash: bool,
                             failed: bool = False) -> None:
        """Record a single command invocation."""
        await self._execute('''
            INSERT INTO command_metrics
                (command_name, cog_name, user_id, guild_id, channel_id, is_slash, failed)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        ''', command_name, cog_name, user_id, guild_id, channel_id, is_slash, failed)

    async def get_command_counts(self, days: int = 7, limit: int = 15) -> list[dict]:
        """Top commands by usage in the last N days (raw + rolled-up)."""
        rows = await self._fetch('''
            SELECT command_name, SUM(uses) AS uses, SUM(unique_users) AS unique_users
            FROM (
                SELECT command_name, COUNT(*) AS uses,
                       COUNT(DISTINCT user_id) AS unique_users
                FROM command_metrics
                WHERE invoked_at > NOW() - MAKE_INTERVAL(days => $1)
                  AND failed = FALSE
                GROUP BY command_name
                UNION ALL
                SELECT command_name, uses, unique_users
                FROM metrics_daily
                WHERE date > CURRENT_DATE - $1
                  AND date <= CURRENT_DATE - 30
            ) combined
            GROUP BY command_name
            ORDER BY uses DESC
            LIMIT $2
        ''', days, limit)
        return [dict(r) for r in rows]

    async def get_hourly_distribution(self, days: int = 7) -> list[dict]:
        """Command usage by hour of day (UTC) over last N days."""
        rows = await self._fetch('''
            SELECT EXTRACT(HOUR FROM invoked_at)::int AS hour,
                   COUNT(*) AS uses
            FROM command_metrics
            WHERE invoked_at > NOW() - MAKE_INTERVAL(days => $1)
              AND failed = FALSE
            GROUP BY hour
            ORDER BY hour
        ''', days)
        return [dict(r) for r in rows]

    async def get_metrics_summary(self, days: int = 7) -> dict:
        """Aggregate metrics summary for the last N days."""
        row = await self._fetchrow('''
            SELECT COUNT(*) AS total_commands,
                   COUNT(DISTINCT user_id) AS unique_users,
                   COUNT(DISTINCT command_name) AS unique_commands,
                   COUNT(*) FILTER (WHERE failed) AS failed_commands
            FROM command_metrics
            WHERE invoked_at > NOW() - MAKE_INTERVAL(days => $1)
        ''', days)
        return dict(row) if row else {}

    async def get_user_top_commands(self, user_id: int, days: int = 7,
                                    limit: int = 5) -> list[dict]:
        """Top commands for a specific user."""
        rows = await self._fetch('''
            SELECT command_name, COUNT(*) as uses
            FROM command_metrics
            WHERE user_id = $1
              AND invoked_at > NOW() - MAKE_INTERVAL(days => $2)
              AND failed = FALSE
            GROUP BY command_name
            ORDER BY uses DESC
            LIMIT $3
        ''', user_id, days, limit)
        return [dict(r) for r in rows]

    # ── Retention / rollup ──

    async def rollup_and_purge_metrics(self, retention_days: int = 30) -> dict:
        """
        Roll up command_metrics older than retention_days into metrics_daily,
        then delete the raw rows. Returns counts of rows rolled up and deleted.
        """
        self._check_pool()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Roll up into daily summary
                rolled = await conn.execute('''
                    INSERT INTO metrics_daily (date, command_name, cog_name, uses, unique_users, failures)
                    SELECT invoked_at::date AS date,
                           command_name,
                           cog_name,
                           COUNT(*) AS uses,
                           COUNT(DISTINCT user_id) AS unique_users,
                           COUNT(*) FILTER (WHERE failed) AS failures
                    FROM command_metrics
                    WHERE invoked_at < NOW() - MAKE_INTERVAL(days => $1)
                    GROUP BY invoked_at::date, command_name, cog_name
                    ON CONFLICT (date, command_name) DO UPDATE
                    SET uses = metrics_daily.uses + EXCLUDED.uses,
                        unique_users = GREATEST(metrics_daily.unique_users, EXCLUDED.unique_users),
                        failures = metrics_daily.failures + EXCLUDED.failures
                ''', retention_days)

                # Delete raw rows that were rolled up
                deleted = await conn.execute('''
                    DELETE FROM command_metrics
                    WHERE invoked_at < NOW() - MAKE_INTERVAL(days => $1)
                ''', retention_days)

        rolled_count = int(rolled.split()[-1]) if rolled else 0
        deleted_count = int(deleted.split()[-1]) if deleted else 0
        logger.info(f"Metrics rollup: {rolled_count} summaries upserted, {deleted_count} raw rows purged")
        return {'rolled_up': rolled_count, 'purged': deleted_count}

    async def purge_old_league_activity(self) -> int:
        """
        Delete leaderboard_activity rows from rounds that are 2+ rounds
        behind the current active round. Keeps current + previous round.
        """
        result = await self._execute('''
            DELETE FROM leaderboard_activity
            WHERE round_id IS NOT NULL
              AND round_id < (
                  SELECT COALESCE(MAX(round_id), 0) - 1
                  FROM league_rounds
              )
        ''')
        count = int(result.split()[-1]) if result else 0
        if count:
            logger.info(f"Purged {count} old leaderboard_activity rows")
        return count

    async def get_table_sizes(self) -> list[dict]:
        """Get row counts for high-volume tables."""
        rows = await self._fetch('''
            SELECT relname AS table_name,
                   n_live_tup AS row_count
            FROM pg_stat_user_tables
            WHERE relname IN (
                'command_metrics', 'metrics_daily',
                'leaderboard_activity', 'conversations'
            )
            ORDER BY n_live_tup DESC
        ''')
        return [dict(r) for r in rows]
