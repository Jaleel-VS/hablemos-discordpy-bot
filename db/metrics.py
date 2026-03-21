"""Database mixin for command metrics and cog management."""
import logging
from datetime import datetime, timezone

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
        """Top commands by usage in the last N days."""
        rows = await self._fetch('''
            SELECT command_name, COUNT(*) as uses,
                   COUNT(DISTINCT user_id) as unique_users
            FROM command_metrics
            WHERE invoked_at > NOW() - MAKE_INTERVAL(days => $1)
              AND failed = FALSE
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
