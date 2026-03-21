"""
Admin cog — owner-only commands for cog management and bot metrics.
"""
import logging
import os

import discord
from discord.ext import commands, tasks
from discord import Embed, Color

from base_cog import BaseCog

logger = logging.getLogger(__name__)

# Extensions that cannot be disabled (would lock you out)
PROTECTED_EXTENSIONS = {'cogs.admin_cog.main'}

# How many days of raw command_metrics to keep before rolling up
METRICS_RETENTION_DAYS = 30


def _discover_extensions() -> list[str]:
    """Return all discoverable cog extension paths."""
    extensions = []
    for folder in os.listdir('./cogs'):
        if folder.endswith('_cog'):
            cog_path = f'./cogs/{folder}'
            if os.path.isdir(cog_path):
                for file in os.listdir(cog_path):
                    if file.endswith('.py') and file.startswith('main'):
                        extensions.append(f'cogs.{folder}.{file[:-3]}')
    return sorted(extensions)


class AdminCog(BaseCog):
    """Owner-only cog management and metrics."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.daily_cleanup.start()

    async def cog_unload(self):
        self.daily_cleanup.cancel()

    # ── Daily cleanup task ──

    @tasks.loop(hours=24)
    async def daily_cleanup(self):
        """Roll up old metrics and purge stale leaderboard activity."""
        try:
            result = await self.bot.db.rollup_and_purge_metrics(METRICS_RETENTION_DAYS)
            league_purged = await self.bot.db.purge_old_league_activity()
            logger.info(
                f"Daily cleanup: metrics rolled={result['rolled_up']} "
                f"purged={result['purged']}, league_activity purged={league_purged}"
            )
        except Exception as e:
            logger.error(f"Daily cleanup failed: {e}", exc_info=True)

    @daily_cleanup.before_loop
    async def before_daily_cleanup(self):
        await self.bot.wait_until_ready()

    # ── Cog management ──

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def cog(self, ctx: commands.Context):
        """Manage bot cogs. Subcommands: list, enable, disable"""
        await ctx.invoke(self.list_cogs)

    @cog.command(name='list')
    @commands.is_owner()
    async def list_cogs(self, ctx: commands.Context):
        """List all cogs and their status."""
        extensions = _discover_extensions()
        disabled = await self.bot.db.get_disabled_cogs()
        loaded = set(self.bot.extensions.keys())

        lines = []
        for ext in extensions:
            short = ext.replace('cogs.', '').replace('.main', '')
            if ext in PROTECTED_EXTENSIONS:
                status = 'loaded (protected)'
            elif ext in disabled:
                status = 'disabled'
            elif ext in loaded:
                status = 'loaded'
            else:
                status = 'unloaded'
            lines.append(f"`{short}` — {status}")

        embed = Embed(
            title="Cog Status",
            description='\n'.join(lines),
            color=Color.blurple(),
        )
        await ctx.send(embed=embed)

    @cog.command(name='enable')
    @commands.is_owner()
    async def enable_cog(self, ctx: commands.Context, name: str):
        """Enable and load a cog. Usage: $cog enable league_cog"""
        ext = f'cogs.{name}.main' if not name.startswith('cogs.') else name

        await self.bot.db.set_cog_enabled(ext, True)

        if ext not in self.bot.extensions:
            try:
                await self.bot.load_extension(ext)
            except Exception as e:
                await ctx.send(f"Enabled in DB but failed to load: {e}")
                return

        await ctx.send(f"Enabled and loaded `{name}`.")
        logger.info(f"Cog enabled: {ext} by {ctx.author}")

    @cog.command(name='disable')
    @commands.is_owner()
    async def disable_cog(self, ctx: commands.Context, name: str):
        """Disable and unload a cog. Usage: $cog disable league_cog"""
        ext = f'cogs.{name}.main' if not name.startswith('cogs.') else name

        if ext in PROTECTED_EXTENSIONS:
            await ctx.send("That cog is protected and cannot be disabled.")
            return

        await self.bot.db.set_cog_enabled(ext, False)

        if ext in self.bot.extensions:
            try:
                await self.bot.unload_extension(ext)
            except Exception as e:
                await ctx.send(f"Disabled in DB but failed to unload: {e}")
                return

        await ctx.send(f"Disabled and unloaded `{name}`.")
        logger.info(f"Cog disabled: {ext} by {ctx.author}")

    @cog.command(name='reload')
    @commands.is_owner()
    async def reload_cog(self, ctx: commands.Context, name: str):
        """Reload a cog. Usage: $cog reload league_cog"""
        ext = f'cogs.{name}.main' if not name.startswith('cogs.') else name

        try:
            await self.bot.reload_extension(ext)
            await ctx.send(f"Reloaded `{name}`.")
            logger.info(f"Cog reloaded: {ext} by {ctx.author}")
        except Exception as e:
            await ctx.send(f"Failed to reload: {e}")

    # ── Metrics ──

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def metrics(self, ctx: commands.Context, days: int = 7):
        """Show bot usage metrics. Usage: $metrics [days]"""
        days = max(1, min(days, 90))

        summary = await self.bot.db.get_metrics_summary(days)
        top_commands = await self.bot.db.get_command_counts(days, limit=10)

        embed = Embed(
            title=f"Bot Metrics — Last {days} day{'s' if days != 1 else ''}",
            color=Color.blurple(),
        )

        # Summary
        total = summary.get('total_commands', 0)
        users = summary.get('unique_users', 0)
        cmds = summary.get('unique_commands', 0)
        failed = summary.get('failed_commands', 0)
        error_rate = (failed / total * 100) if total else 0

        embed.add_field(
            name="Overview",
            value=(
                f"**Total invocations:** {total:,}\n"
                f"**Unique users:** {users:,}\n"
                f"**Unique commands:** {cmds}\n"
                f"**Error rate:** {error_rate:.1f}%"
            ),
            inline=False,
        )

        # Top commands
        if top_commands:
            lines = []
            for i, cmd in enumerate(top_commands, 1):
                lines.append(
                    f"`{i:>2}.` **{cmd['command_name']}** — "
                    f"{cmd['uses']:,} uses ({cmd['unique_users']} users)"
                )
            embed.add_field(
                name="Top Commands",
                value='\n'.join(lines),
                inline=False,
            )

        await ctx.send(embed=embed)

    @metrics.command(name='hours')
    @commands.is_owner()
    async def metrics_hours(self, ctx: commands.Context, days: int = 7):
        """Show command usage by hour (UTC). Usage: $metrics hours [days]"""
        days = max(1, min(days, 90))
        hourly = await self.bot.db.get_hourly_distribution(days)

        if not hourly:
            await ctx.send("No data yet.")
            return

        # Build a simple bar chart
        hour_map = {h['hour']: h['uses'] for h in hourly}
        max_uses = max(hour_map.values()) if hour_map else 1

        lines = []
        for h in range(24):
            uses = hour_map.get(h, 0)
            bar_len = round(uses / max_uses * 12) if max_uses else 0
            bar = '█' * bar_len
            lines.append(f"`{h:02d}:00` {bar} {uses}")

        embed = Embed(
            title=f"Usage by Hour (UTC) — Last {days}d",
            description='\n'.join(lines),
            color=Color.blurple(),
        )
        await ctx.send(embed=embed)

    @metrics.command(name='user')
    @commands.is_owner()
    async def metrics_user(self, ctx: commands.Context, member: discord.Member, days: int = 7):
        """Show top commands for a user. Usage: $metrics user @someone [days]"""
        days = max(1, min(days, 90))
        top = await self.bot.db.get_user_top_commands(member.id, days)

        if not top:
            await ctx.send(f"No command data for {member.display_name} in the last {days} days.")
            return

        lines = [f"**{c['command_name']}** — {c['uses']} uses" for c in top]
        embed = Embed(
            title=f"Commands by {member.display_name} — Last {days}d",
            description='\n'.join(lines),
            color=Color.blurple(),
        )
        await ctx.send(embed=embed)

    @metrics.command(name='retention')
    @commands.is_owner()
    async def metrics_retention(self, ctx: commands.Context):
        """Show table sizes and retention info."""
        sizes = await self.bot.db.get_table_sizes()

        embed = Embed(
            title="Data Retention",
            color=Color.blurple(),
        )

        if sizes:
            lines = [f"`{t['table_name']}` — {t['row_count']:,} rows" for t in sizes]
            embed.add_field(name="Table Sizes", value='\n'.join(lines), inline=False)
        else:
            embed.add_field(name="Table Sizes", value="No data available (stats may need a vacuum).", inline=False)

        embed.add_field(
            name="Policy",
            value=(
                f"**command_metrics:** raw rows kept {METRICS_RETENTION_DAYS} days, then rolled up to metrics_daily\n"
                f"**leaderboard_activity:** purged for rounds older than current - 1\n"
                f"**Cleanup runs:** every 24 hours"
            ),
            inline=False,
        )

        await ctx.send(embed=embed)

    @metrics.command(name='cleanup')
    @commands.is_owner()
    async def metrics_cleanup(self, ctx: commands.Context):
        """Manually trigger the daily cleanup."""
        msg = await ctx.send("Running cleanup...")
        result = await self.bot.db.rollup_and_purge_metrics(METRICS_RETENTION_DAYS)
        league_purged = await self.bot.db.purge_old_league_activity()
        await msg.edit(
            content=(
                f"Done. Metrics: {result['rolled_up']} rolled up, {result['purged']} purged. "
                f"League activity: {league_purged} purged."
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
