"""
Admin cog — owner-only commands for cog management and bot metrics.
"""
import logging
import os
from datetime import UTC, datetime, timedelta

import discord
from discord import Color, Embed
from discord.ext import commands, tasks

from base_cog import BaseCog

logger = logging.getLogger(__name__)

# Extensions that cannot be disabled (would lock you out)
PROTECTED_EXTENSIONS = {'cogs.admin_cog.main'}

# How many days of raw command_metrics to keep before rolling up
METRICS_RETENTION_DAYS = 30

# How many days of interaction rows to keep
INTERACTIONS_RETENTION_DAYS = 90


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
        self._interaction_errors = 0

    async def cog_unload(self):
        self.daily_cleanup.cancel()

    # ── Interaction tracking (on_message) ──

    async def _record(self, channel_id: int, guild_id: int, author_id: int, target_id: int, kind: str) -> None:
        """Record an interaction, suppressing repeated DB errors to avoid log spam."""
        try:
            await self.bot.db.record_interaction(channel_id, guild_id, author_id, target_id, kind)
            self._interaction_errors = 0
        except Exception:
            self._interaction_errors += 1
            if self._interaction_errors <= 3:
                logger.exception("Failed to record %s interaction", kind)
            elif self._interaction_errors == 4:
                logger.error("Suppressing further interaction recording errors")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track reply and mention interactions to the database."""
        if message.author.bot or not message.guild:
            return

        author_id = message.author.id
        channel_id = message.channel.id
        guild_id = message.guild.id

        # Track replies
        replied_to_id = None
        ref = message.reference
        if ref and ref.resolved and not isinstance(ref.resolved, discord.DeletedReferencedMessage):
            target = ref.resolved.author
            if not target.bot and target.id != author_id:
                replied_to_id = target.id
                await self._record(channel_id, guild_id, author_id, target.id, "reply")

        # Track mentions (skip the reply target — Discord auto-mentions them)
        for mentioned in message.mentions:
            if not mentioned.bot and mentioned.id != author_id and mentioned.id != replied_to_id:
                await self._record(channel_id, guild_id, author_id, mentioned.id, "mention")

    # ── Daily cleanup task ──

    @tasks.loop(hours=24)
    async def daily_cleanup(self):
        """Roll up old metrics and purge stale data."""
        try:
            result = await self.bot.db.rollup_and_purge_metrics(METRICS_RETENTION_DAYS)
            league_purged = await self.bot.db.purge_old_league_activity()
            interactions_purged = await self.bot.db.purge_old_interactions(INTERACTIONS_RETENTION_DAYS)
            logger.info(
                "Daily cleanup: metrics rolled=%s purged=%s, "
                "league_activity purged=%s, interactions purged=%s",
                result['rolled_up'], result['purged'],
                league_purged, interactions_purged,
            )
        except Exception:
            logger.exception("Daily cleanup failed")

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
        logger.info("Cog enabled: %s by %s", ext, ctx.author.id)

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
        logger.info("Cog disabled: %s by %s", ext, ctx.author.id)

    @cog.command(name='reload')
    @commands.is_owner()
    async def reload_cog(self, ctx: commands.Context, name: str):
        """Reload a cog. Usage: $cog reload league_cog"""
        ext = f'cogs.{name}.main' if not name.startswith('cogs.') else name

        try:
            await self.bot.reload_extension(ext)
            await ctx.send(f"Reloaded `{name}`.")
            logger.info("Cog reloaded: %s by %s", ext, ctx.author.id)
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
                f"**interactions:** raw rows kept {INTERACTIONS_RETENTION_DAYS} days\n"
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
        interactions_purged = await self.bot.db.purge_old_interactions(INTERACTIONS_RETENTION_DAYS)
        await msg.edit(
            content=(
                f"Done. Metrics: {result['rolled_up']} rolled up, {result['purged']} purged. "
                f"League activity: {league_purged} purged. "
                f"Interactions: {interactions_purged} purged."
            )
        )

    # ── Server info ──

    @commands.command(name='mystats')
    @commands.is_owner()
    async def mystats(self, ctx: commands.Context):
        """Show servers the bot is in."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        lines = []
        for g in guilds:
            joined = g.me.joined_at
            joined_str = f"<t:{int(joined.timestamp())}:R>" if joined else "?"
            lines.append(f"**{g.name}** — {g.member_count:,} members, joined {joined_str}")

        embed = Embed(
            title=f"Servers ({len(guilds)})",
            description='\n'.join(lines) or "Not in any servers.",
            color=Color.blurple(),
        )
        await ctx.send(embed=embed)

    # ── Interaction analysis ──

    @commands.command(name='interactions')
    @commands.is_owner()
    async def interactions(self, ctx: commands.Context, channel: discord.TextChannel = None, days: int = 7):
        """
        Show top reply/mention pairs in a channel (from tracked data).

        Usage: $interactions [#channel] [days]
        """
        channel = channel or ctx.channel
        days = max(1, min(days, 90))
        after = datetime.now(UTC) - timedelta(days=days)

        top_pairs = await self.bot.db.get_top_pairs(channel.id, after)
        stats = await self.bot.db.get_interaction_stats(channel.id, after)

        if not top_pairs:
            await ctx.send(f"No interactions recorded in #{channel.name} over the last {days} days.")
            return

        # Resolve display names for all user IDs in the results
        user_ids: set[int] = set()
        for pair in top_pairs:
            user_ids.add(pair['user_a'])
            user_ids.add(pair['user_b'])

        names: dict[int, str] = {}
        guild = ctx.guild
        for uid in user_ids:
            member = guild.get_member(uid) if guild else None
            names[uid] = member.display_name if member else f"User {uid}"

        # Build embed
        lines = []
        for i, pair in enumerate(top_pairs, 1):
            parts = []
            if pair['replies']:
                r = pair['replies']
                parts.append(f"{r} {'reply' if r == 1 else 'replies'}")
            if pair['mentions']:
                m = pair['mentions']
                parts.append(f"{m} {'mention' if m == 1 else 'mentions'}")
            lines.append(
                f"`{i:>2}.` **{names[pair['user_a']]}** & **{names[pair['user_b']]}** — {', '.join(parts)}"
            )

        embed = Embed(
            title=f"Interactions in #{channel.name}",
            description=f"Last {days} days",
            color=Color.blurple(),
        )
        embed.add_field(name="Top Pairs", value='\n'.join(lines), inline=False)
        embed.add_field(
            name="Stats",
            value=(
                f"**{stats['unique_pairs']}** unique pairs — "
                f"**{stats['total_replies']}** replies, "
                f"**{stats['total_mentions']}** mentions"
            ),
            inline=False,
        )

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
