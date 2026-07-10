"""Stats cog — server activity tracking and admin analytics.

Tracks message counts by channel and native-role type (hourly buckets),
plus user adoption (first_seen / last_seen). Admin-only ``$stats`` command
group with text summaries and matplotlib graph attachments.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import red_embed

from . import graphs
from .config import ROLE_MAP

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Track every non-bot message for stats."""
        if message.author.bot:
            return
        if not message.guild:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return

        role_type = _classify_role(member)
        hour_bucket = _truncate_hour(datetime.now(UTC))

        try:
            await self.bot.db.upsert_channel_stat(
                message.channel.id, role_type, hour_bucket
            )
            await self.bot.db.upsert_user_activity(member.id, role_type)
        except Exception as e:
            logger.debug("Stats upsert failed: %s", e)

    # ── $stats command group ──

    @commands.group(name="stats", invoke_without_command=True)
    @commands.is_owner()
    async def stats(self, ctx: commands.Context, days: int = 7):
        """Show server stats summary. Usage: $stats [days]"""
        days = max(1, min(days, 90))

        top_channels = await self.bot.db.get_top_channels(days, limit=5)
        role_data = await self.bot.db.get_role_breakdown(days)
        growth = await self.bot.db.get_growth_summary(days)

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
            from .config import ROLE_LABELS
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

    @stats.command(name="channels")
    @commands.is_owner()
    async def stats_channels(self, ctx: commands.Context, days: int = 7):
        """Top channels bar chart. Usage: $stats channels [days]"""
        days = max(1, min(days, 90))
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

    @stats.command(name="roles")
    @commands.is_owner()
    async def stats_roles(self, ctx: commands.Context, days: int = 7):
        """Daily activity by role stacked bar chart. Usage: $stats roles [days]"""
        days = max(1, min(days, 90))
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
        growth = await self.bot.db.get_growth_summary(30)

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
        days = max(1, min(days, 90))
        data = await self.bot.db.get_hourly_heatmap(days)

        if not data:
            await ctx.send(embed=red_embed("No heatmap data yet."))
            return

        buf = await asyncio.to_thread(graphs.render_heatmap, data, days)
        file = discord.File(buf, filename="heatmap.png")
        embed = discord.Embed(title=f"📊 Activity Heatmap — Last {days} days", color=0x5865F2)
        embed.set_image(url="attachment://heatmap.png")
        await ctx.send(embed=embed, file=file)


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    await bot.add_cog(StatsCog(bot))
    logger.info("StatsCog loaded successfully")
