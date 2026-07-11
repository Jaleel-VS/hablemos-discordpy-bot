"""Stats cog — server activity tracking and admin analytics.

Tracks message counts by channel and native-role type (hourly buckets),
plus user adoption (first_seen / last_seen). Admin-only ``$stats`` command
group with text summaries and matplotlib graph attachments.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.utils.embeds import red_embed

from . import graphs
from .config import (
    ROLE_LABELS,
    ROLE_MAP,
    STATS_GUILD_ID,
    STATS_REPORT_CHANNEL_ID,
    STATS_WEEKLY_REPORT_DAY,
    STATS_WEEKLY_REPORT_HOUR_UTC,
)

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_MAX_STATS_DAYS = 90
_STATS_ERROR_LOG_INTERVAL = timedelta(minutes=5)
_DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _classify_role(member: discord.Member) -> str:
    """Classify a member by their native language role."""
    role_ids = {r.id for r in member.roles}
    for role_id, role_type in ROLE_MAP.items():
        if role_id in role_ids:
            return role_type
    return "other_native"


def _truncate_hour(dt: datetime) -> datetime:
    """Truncate a datetime to the hour (for bucketing)."""
    return dt.replace(minute=0, second=0, microsecond=0)


class StatsCog(BaseCog):
    """Server activity tracking and analytics."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        self._last_stats_warning_at: datetime | None = None
        self._stats_error_count = 0
        self._last_weekly_report_date: date | None = None
        self.weekly_report.start()

    def cog_unload(self) -> None:
        """Stop scheduled report task on unload."""
        self.weekly_report.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Restrict all $stats commands to the tracked guild."""
        return ctx.guild is not None and ctx.guild.id == STATS_GUILD_ID

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Track every non-bot message for stats."""
        if message.author.bot:
            return
        if not message.guild or message.guild.id != STATS_GUILD_ID:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return

        role_type = _classify_role(member)
        hour_bucket = _truncate_hour(datetime.now(UTC))

        try:
            await self.bot.db.track_message_stats(
                message.channel.id,
                member.id,
                role_type,
                hour_bucket,
            )
        except Exception as e:
            self._log_stats_tracking_error(e)

    def _log_stats_tracking_error(self, exc: Exception) -> None:
        """Rate-limit noisy stats write failures from the message hot path."""
        now = datetime.now(UTC)
        self._stats_error_count += 1
        if (
            self._last_stats_warning_at is not None
            and now - self._last_stats_warning_at < _STATS_ERROR_LOG_INTERVAL
        ):
            return

        logger.warning(
            "Stats tracking failed %s time(s) since last warning: %s",
            self._stats_error_count,
            exc,
            exc_info=True,
        )
        self._last_stats_warning_at = now
        self._stats_error_count = 0

    @tasks.loop(hours=1)
    async def weekly_report(self) -> None:
        """Post a weekly stats report when configured."""
        if STATS_REPORT_CHANNEL_ID <= 0:
            return

        now = datetime.now(UTC)
        if (
            now.weekday() != STATS_WEEKLY_REPORT_DAY
            or now.hour != STATS_WEEKLY_REPORT_HOUR_UTC
            or self._last_weekly_report_date == now.date()
        ):
            return

        guild = self.bot.get_guild(STATS_GUILD_ID)
        if guild is None:
            logger.warning("Stats weekly report guild %s not found", STATS_GUILD_ID)
            return

        channel = guild.get_channel(STATS_REPORT_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning("Stats weekly report channel %s not found", STATS_REPORT_CHANNEL_ID)
            return

        embed = await self._build_report_embed(guild, days=7)
        await channel.send(embed=embed)
        self._last_weekly_report_date = now.date()

    @weekly_report.before_loop
    async def before_weekly_report(self) -> None:
        """Wait until the bot is ready before scheduled reporting."""
        await self.bot.wait_until_ready()

    # ── $stats command group ──

    @commands.group(name="stats", invoke_without_command=True)
    @commands.is_owner()
    async def stats(self, ctx: commands.Context, days: int = 7):
        """Show server stats summary. Usage: $stats [days]"""
        days = _clamp_days(days)

        top_channels = await self.bot.db.get_top_channels(days, limit=5)
        role_data = await self.bot.db.get_role_breakdown(days)
        growth = await self.bot.db.get_growth_summary(new_user_days=days)

        # Build summary embed
        embed = discord.Embed(
            title=f"📊 Server Stats — Last {days} days",
            color=0x5865F2,
        )

        # Top channels
        if top_channels:
            channel_lines = []
            for i, row in enumerate(top_channels, 1):
                ch = ctx.guild.get_channel(row["channel_id"]) if ctx.guild else None
                name = f"#{ch.name}" if ch else f"#{row['channel_id']}"
                channel_lines.append(f"`{i}.` {name} — **{row['total']:,}** msgs")
            embed.add_field(
                name="🏆 Top Channels",
                value="\n".join(channel_lines),
                inline=False,
            )

        # Role breakdown
        if role_data:
            role_lines = [
                f"**{ROLE_LABELS.get(r['role_type'], r['role_type'])}:** {r['total']:,}"
                for r in role_data
            ]
            embed.add_field(
                name="👥 Messages by Role",
                value="\n".join(role_lines),
                inline=True,
            )

        # Growth
        embed.add_field(
            name="📈 Users",
            value=(
                f"**Total:** {growth['total_users']:,}\n"
                f"**MAU (30d):** {growth['monthly_active']:,}\n"
                f"**New ({days}d):** {growth['new_users']:,}"
            ),
            inline=True,
        )

        await ctx.send(embed=embed)

    @stats.command(name="report")
    @commands.is_owner()
    async def stats_report(self, ctx: commands.Context, days: int = 7):
        """Period-over-period server health report. Usage: $stats report [days]"""
        days = _clamp_days(days)
        embed = await self._build_report_embed(ctx.guild, days)
        await ctx.send(embed=embed)

    @stats.command(name="channels")
    @commands.is_owner()
    async def stats_channels(self, ctx: commands.Context, days: int = 7):
        """Top channels bar chart. Usage: $stats channels [days]"""
        days = _clamp_days(days)
        data = await self.bot.db.get_top_channels(days, limit=10)

        if not data:
            await ctx.send(embed=red_embed("No channel data yet."))
            return

        # Resolve channel names
        channel_names: dict[int, str] = {}
        for row in data:
            ch = ctx.guild.get_channel(row["channel_id"]) if ctx.guild else None
            channel_names[row["channel_id"]] = f"#{ch.name}" if ch else f"#{row['channel_id']}"

        buf = await asyncio.to_thread(
            graphs.render_top_channels, data, channel_names, days
        )
        file = discord.File(buf, filename="top_channels.png")
        embed = discord.Embed(title=f"📊 Top Channels — Last {days} days", color=0x5865F2)
        embed.set_image(url="attachment://top_channels.png")
        await ctx.send(embed=embed, file=file)

    @stats.command(name="topusers")
    @commands.is_owner()
    async def stats_topusers(self, ctx: commands.Context, days: int = 7):
        """Top active users leaderboard. Usage: $stats topusers [days]"""
        days = _clamp_days(days)
        data = await self.bot.db.get_top_users(days, limit=10)

        if not data:
            await ctx.send(embed=red_embed("No user activity data yet."))
            return

        user_lines = []
        for i, row in enumerate(data, 1):
            member = ctx.guild.get_member(row["user_id"]) if ctx.guild else None
            name = member.display_name if member else f"<@{row['user_id']}>"
            total = int(row["total"])
            active_days = int(row["active_days"])
            per_day = _safe_average(total, active_days)
            user_lines.append(
                f"`{i}.` {name} — **{total:,}** msgs · "
                f"{active_days} active days · {per_day:.1f}/day"
            )

        embed = discord.Embed(
            title=f"📊 Top Users — Last {days} days",
            color=0x5865F2,
        )
        embed.add_field(name="🏆 Most Active", value="\n".join(user_lines), inline=False)
        await ctx.send(embed=embed)

    @stats.command(name="roles")
    @commands.is_owner()
    async def stats_roles(self, ctx: commands.Context, days: int = 7):
        """Daily activity by role stacked bar chart. Usage: $stats roles [days]"""
        days = _clamp_days(days)
        data = await self.bot.db.get_daily_activity(days)

        if not data:
            await ctx.send(embed=red_embed("No activity data yet."))
            return

        buf = await asyncio.to_thread(graphs.render_role_daily, data, days)
        file = discord.File(buf, filename="role_daily.png")
        embed = discord.Embed(title=f"📊 Daily Activity by Role — Last {days} days", color=0x5865F2)
        embed.set_image(url="attachment://role_daily.png")
        await ctx.send(embed=embed, file=file)

    @stats.command(name="growth")
    @commands.is_owner()
    async def stats_growth(self, ctx: commands.Context, weeks: int = 8):
        """User growth chart. Usage: $stats growth [weeks]"""
        weeks = max(1, min(weeks, 52))
        weekly_data = await self.bot.db.get_new_users_per_week(weeks)
        growth = await self.bot.db.get_growth_summary(new_user_days=30)

        if not weekly_data:
            await ctx.send(embed=red_embed("No user data yet."))
            return

        buf = await asyncio.to_thread(
            graphs.render_growth,
            weekly_data,
            growth["total_users"],
            growth["monthly_active"],
        )
        file = discord.File(buf, filename="growth.png")
        embed = discord.Embed(title=f"📊 User Growth — Last {weeks} weeks", color=0x5865F2)
        embed.set_image(url="attachment://growth.png")
        await ctx.send(embed=embed, file=file)

    @stats.command(name="heatmap")
    @commands.is_owner()
    async def stats_heatmap(self, ctx: commands.Context, days: int = 7):
        """Activity heatmap (hour × day). Usage: $stats heatmap [days]"""
        days = _clamp_days(days)
        data = await self.bot.db.get_hourly_heatmap(days)

        if not data:
            await ctx.send(embed=red_embed("No heatmap data yet."))
            return

        buf = await asyncio.to_thread(graphs.render_heatmap, data, days)
        file = discord.File(buf, filename="heatmap.png")
        embed = discord.Embed(title=f"📊 Activity Heatmap — Last {days} days", color=0x5865F2)
        embed.set_image(url="attachment://heatmap.png")
        await ctx.send(embed=embed, file=file)

    async def _build_report_embed(
        self, guild: discord.Guild | None, days: int
    ) -> discord.Embed:
        """Build the period-over-period stats report embed."""
        now = datetime.now(UTC)
        current_start = now - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)

        current = await self.bot.db.get_activity_totals_between(current_start, now)
        previous = await self.bot.db.get_activity_totals_between(
            previous_start, current_start
        )
        channel_deltas = await self.bot.db.get_channel_period_deltas(
            current_start,
            now,
            previous_start,
            current_start,
        )
        role_deltas = await self.bot.db.get_role_period_deltas(
            current_start,
            now,
            previous_start,
            current_start,
        )
        peak = await self.bot.db.get_peak_activity_window(current_start, now)

        embed = discord.Embed(
            title=f"📊 Stats Report — Last {days} days",
            description=f"Compared with the previous {days} days.",
            color=0x5865F2,
        )

        current_messages = int(current["total_messages"])
        previous_messages = int(previous["total_messages"])
        current_active = int(current["active_users"])
        previous_active = int(previous["active_users"])
        current_new = int(current["new_users"])
        previous_new = int(previous["new_users"])
        current_mpau = _safe_average(current_messages, current_active)
        previous_mpau = _safe_average(previous_messages, previous_active)

        embed.add_field(
            name="Overview",
            value=(
                f"**Messages:** {_format_metric(current_messages, previous_messages)}\n"
                f"**Active users:** {_format_metric(current_active, previous_active)}\n"
                f"**New users:** {_format_metric(current_new, previous_new)}\n"
                f"**Msgs / active user:** {_format_float_metric(current_mpau, previous_mpau)}"
            ),
            inline=False,
        )

        rising = [row for row in channel_deltas if int(row["delta"]) > 0][:3]
        falling = [row for row in channel_deltas if int(row["delta"]) < 0]
        falling = sorted(falling, key=lambda row: int(row["delta"]))[:3]

        embed.add_field(
            name="Rising Channels",
            value=_format_channel_delta_lines(guild, rising, rising=True),
            inline=True,
        )
        embed.add_field(
            name="Cooling Channels",
            value=_format_channel_delta_lines(guild, falling, rising=False),
            inline=True,
        )

        if role_deltas:
            role_lines = [
                (
                    f"**{ROLE_LABELS.get(row['role_type'], row['role_type'])}:** "
                    f"{int(row['current_total']):,} "
                    f"({_format_delta(int(row['current_total']), int(row['previous_total']))})"
                )
                for row in role_deltas
            ]
            embed.add_field(
                name="Role Mix",
                value="\n".join(role_lines),
                inline=False,
            )

        peak_text = _format_peak_window(peak)
        embed.add_field(name="Peak Window", value=peak_text, inline=False)
        return embed


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(StatsCog(bot))
    logger.info("StatsCog loaded successfully")


def _clamp_days(days: int) -> int:
    """Clamp user-provided day windows to the supported range."""
    return max(1, min(days, _MAX_STATS_DAYS))


def _safe_average(numerator: int, denominator: int) -> float:
    """Return an average with a zero-denominator guard."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _format_metric(current: int, previous: int) -> str:
    """Format an integer metric with a period-over-period delta."""
    return f"{current:,} ({_format_delta(current, previous)})"


def _format_float_metric(current: float, previous: float) -> str:
    """Format a decimal metric with a period-over-period delta."""
    return f"{current:.1f} ({_format_float_delta(current, previous)})"


def _format_delta(current: int, previous: int) -> str:
    """Format a signed integer delta and percentage change."""
    delta = current - previous
    sign = "+" if delta > 0 else ""
    if previous == 0:
        return f"{sign}{delta:,}" if delta else "0"
    pct = delta / previous * 100
    return f"{sign}{delta:,}, {pct:+.0f}%"


def _format_float_delta(current: float, previous: float) -> str:
    """Format a signed float delta and percentage change."""
    delta = current - previous
    sign = "+" if delta > 0 else ""
    if previous == 0:
        return f"{sign}{delta:.1f}" if delta else "0.0"
    pct = delta / previous * 100
    return f"{sign}{delta:.1f}, {pct:+.0f}%"


def _format_channel_delta_lines(
    guild: discord.Guild | None, rows: list[dict], *, rising: bool
) -> str:
    """Format channel delta rows for the report embed."""
    if not rows:
        return "No change."

    lines = []
    for row in rows:
        current = int(row["current_total"])
        previous = int(row["previous_total"])
        name = _format_channel_name(guild, int(row["channel_id"]))
        marker = "+" if rising else ""
        lines.append(
            f"{name}: **{current:,}** ({marker}{current - previous:,})"
        )
    return "\n".join(lines)


def _format_channel_name(guild: discord.Guild | None, channel_id: int) -> str:
    """Resolve a channel ID for display."""
    channel = guild.get_channel(channel_id) if guild else None
    return f"#{channel.name}" if channel else f"#{channel_id}"


def _format_peak_window(peak: dict) -> str:
    """Format the busiest UTC day/hour window."""
    if peak["dow"] is None or peak["hour"] is None:
        return "No activity in this period."

    dow = int(peak["dow"])
    hour = int(peak["hour"])
    total = int(peak["total"])
    return f"**{_DAY_NAMES[dow]} {hour:02d}:00 UTC** — {total:,} msgs"
