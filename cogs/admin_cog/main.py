"""
Admin cog — owner-only commands for cog management and bot metrics.
"""
import logging
import re
from datetime import UTC, datetime

import discord
from discord import Color, Embed, ui
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.utils.discovery import discover_extensions
from cogs.utils.duration import format_duration, parse_duration
from cogs.utils.plural import plural

logger = logging.getLogger(__name__)

# Extensions that cannot be disabled (would lock you out)
PROTECTED_EXTENSIONS = {'cogs.admin_cog.main'}

# How many days of raw command_metrics to keep before rolling up
METRICS_RETENTION_DAYS = 30

# How many days of interaction rows to keep
INTERACTIONS_RETENTION_DAYS = 90

# Pattern to extract user IDs from Rai voice log embed field values
_PARTICIPANT_RE = re.compile(r'participant-id-is-P(\d+)')
# Pattern to extract the joiner's user ID from the footer text
_JOINER_RE = re.compile(r'^V(\d+)')


class AdminCog(BaseCog):
    """Owner-only cog management and metrics."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.daily_cleanup.start()
        self._interaction_errors = 0
        self._last_interactions_msg: discord.Message | None = None

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
        extensions = discover_extensions()
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
                logger.error("Failed to load extension %s: %s", ext, e, exc_info=True)
                await ctx.send("Enabled in DB but failed to load. Check logs.")
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
                logger.error("Failed to unload extension %s: %s", ext, e, exc_info=True)
                await ctx.send("Disabled in DB but failed to unload. Check logs.")
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
            logger.error("Failed to reload extension: %s", e, exc_info=True)
            await ctx.send("Failed to reload. Check logs.")

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

    @commands.command(name='leave')
    @commands.is_owner()
    async def leave_guild(self, ctx: commands.Context, guild_id: int):
        """Leave a guild by ID. Usage: $leave <guild_id>"""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send(f"Guild `{guild_id}` not found.")
            return
        name = guild.name
        await guild.leave()
        await ctx.send(f"Left **{name}**.")
        logger.info("Left guild %s (%s) by request of %s", name, guild_id, ctx.author.id)

    # ── Interaction analysis ──

    @commands.command(name='interactions')
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def interactions(self, ctx: commands.Context, duration: str = "7d", channel: discord.TextChannel = None):
        """
        Show top reply/mention pairs in a channel (from tracked data).

        Usage: $interactions [duration] [#channel]
        Examples: $interactions 12h | $interactions 3d #general | $interactions 1d12h
        """
        channel = channel or ctx.channel

        try:
            td = parse_duration(duration)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        after = datetime.now(UTC) - td
        duration_label = format_duration(td)

        top_pairs = await self.bot.db.get_top_pairs(channel.id, after)
        stats = await self.bot.db.get_interaction_stats(channel.id, after)

        if not top_pairs:
            await ctx.send(f"No interactions recorded in #{channel.name} over the last {duration_label}.")
            return

        guild = ctx.guild

        def _display_name(uid: int) -> str:
            member = guild.get_member(uid) if guild else None
            if member:
                return member.nick or member.global_name or member.name
            return f"User {uid}"

        MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

        lines = []
        for i, pair in enumerate(top_pairs, 1):
            name_a = _display_name(pair['user_a'])
            name_b = _display_name(pair['user_b'])
            parts = []
            if pair['replies']:
                parts.append(f"{plural(pair['replies']):reply/replies}")
            if pair['mentions']:
                parts.append(f"{plural(pair['mentions']):mention}")
            detail = ", ".join(parts)
            rank = MEDALS.get(i, f"**{i}.**")
            lines.append(f"{rank} {name_a}  &  {name_b}\n-# {detail}")

        view = ui.LayoutView()
        view.add_item(ui.Container(
            ui.TextDisplay(f"## Interactions in #{channel.name}\n-# Top pairs by replies & mentions"),
            ui.Separator(visible=True),
            ui.TextDisplay("\n".join(lines)),
            ui.Separator(visible=True),
            ui.TextDisplay(
                f"**{stats['unique_pairs']}** unique pairs — "
                f"**{stats['total_replies']}** replies, "
                f"**{stats['total_mentions']}** mentions\n"
                f"-# Last {duration_label}"
            ),
            accent_colour=Color.blurple(),
        ))
        await ctx.send(view=view)
        self._last_interactions_msg = ctx.message

    @interactions.error
    async def interactions_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Show cooldown with a jump link to the last invocation."""
        if isinstance(error, commands.CommandOnCooldown):
            msg = f"⏱️ On cooldown — try again in {round(error.retry_after)}s."
            if self._last_interactions_msg:
                msg += f" [Last used here]({self._last_interactions_msg.jump_url})"
            await ctx.send(msg)
            return
        # Let the global handler deal with anything else
        raise error


    # ── Voice channel enrichment ──

    @commands.command(name='vcenrich')
    @commands.is_owner()
    async def vc_enrich(self, ctx: commands.Context, message_link: str):
        """Enrich a Rai voice-join log embed with avatars. Usage: $vcenrich <message_link>"""
        # Parse message link
        parts = message_link.strip().split('/')
        try:
            guild_id = int(parts[-3])
            channel_id = int(parts[-2])
            message_id = int(parts[-1].split('?')[0])
        except (IndexError, ValueError):
            await ctx.send("❌ Invalid message link.")
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send("❌ Bot is not in that server.")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Channel not found.")
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("❌ Message not found.")
            return
        except discord.Forbidden:
            await ctx.send("❌ No permission to read that channel.")
            return
        except discord.HTTPException:
            logger.exception("Failed to fetch message %s", message_id)
            await ctx.send("❌ Failed to fetch message.")
            return

        if not message.embeds:
            await ctx.send("❌ That message has no embeds.")
            return

        embed = message.embeds[0]
        embed_dict = embed.to_dict()

        # Extract joiner ID from footer (e.g. "V638764284670640163 - Voice Join")
        footer_text = embed_dict.get('footer', {}).get('text', '')
        joiner_match = _JOINER_RE.match(footer_text)
        if not joiner_match:
            await ctx.send("❌ Couldn't parse joiner ID from embed footer. Is this a Rai voice log?")
            return
        joiner_id = int(joiner_match.group(1))

        # Extract participant IDs from the field
        fields = embed_dict.get('fields', [])
        if not fields:
            await ctx.send("❌ No participant field found in embed.")
            return

        participant_ids = [int(m) for m in _PARTICIPANT_RE.findall(fields[0].get('value', ''))]
        if not participant_ids:
            await ctx.send("❌ No participant IDs found in embed field.")
            return

        # Extract channel name from description (e.g. "**💬￤Sala 1**")
        desc = embed_dict.get('description', '')
        vc_name_match = re.search(r'\*\*(.+?)\*\*\]', desc)
        vc_name = vc_name_match.group(1) if vc_name_match else "Voice Channel"

        # Build the Components v2 view
        # LayoutView has a global 40-component limit across all containers.
        # Each Section(TextDisplay, accessory=Thumbnail) = 3 components.
        # Container itself = 1, header (TextDisplay + Separator) = 2.
        # Budget per message: (40 - 1 - 2) / 3 = 12 sections max with header,
        # (40 - 1) / 3 = 13 without. Use 10 to leave room for footer.
        MAX_SECTIONS = 10
        accent = Color(embed_dict.get('color', 0x3B9EA3))

        sections: list[ui.Section] = []
        for uid in participant_ids:
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except discord.HTTPException:
                    member = None

            if member:
                avatar_url = member.display_avatar.url
                global_name = member.global_name or member.name
                display_name = member.nick or global_name
                label = f"**{display_name}**"
                if display_name != global_name:
                    label += f"\n-# {global_name}"
                if member.name != global_name:
                    label += f"\n-# @{member.name}"
                label += f"\n```{uid}```"
            else:
                avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
                label = f"**Unknown User**\n```{uid}```"

            if uid == joiner_id:
                label = f"➡️ {label}  *(joined)*"

            sections.append(ui.Section(
                ui.TextDisplay(label),
                accessory=ui.Thumbnail(avatar_url),
            ))

        # Parse timestamp for footer
        ts_text = None
        ts = embed_dict.get('timestamp', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                ts_text = f"-# <t:{int(dt.timestamp())}:R>"
            except ValueError:
                pass

        # Send in batches — each LayoutView gets one Container
        for i in range(0, len(sections), MAX_SECTIONS):
            chunk = sections[i:i + MAX_SECTIONS]
            items: list[ui.Item] = []

            if i == 0:
                items.append(ui.TextDisplay(f"## {vc_name}\n-# {len(participant_ids)} users in channel"))
                items.append(ui.Separator(visible=True))

            items.extend(chunk)

            is_last = i + MAX_SECTIONS >= len(sections)
            if is_last and ts_text:
                items.append(ui.Separator(visible=True))
                items.append(ui.TextDisplay(ts_text))

            view = ui.LayoutView()
            view.add_item(ui.Container(*items, accent_colour=accent))
            await ctx.send(view=view)

    # ── Raw embed output ──

    @commands.command(name='rawembed')
    @commands.is_owner()
    async def raw_embed(self, ctx: commands.Context, message_link: str):
        """Show the raw embed data from a message. Usage: $rawembed <message_link>"""
        parts = message_link.strip().split('/')
        try:
            guild_id = int(parts[-3])
            channel_id = int(parts[-2])
            message_id = int(parts[-1].split('?')[0])
        except (IndexError, ValueError):
            await ctx.send("❌ Invalid message link. Use: `https://discord.com/channels/guild/channel/message`")
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            await ctx.send("❌ Bot is not in that server.")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            await ctx.send("❌ Channel not found or not accessible.")
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("❌ Message not found.")
            return
        except discord.Forbidden:
            await ctx.send("❌ No permission to read that channel.")
            return
        except discord.HTTPException:
            logger.exception("Failed to fetch message %s", message_id)
            await ctx.send("❌ Failed to fetch message.")
            return

        if not message.embeds:
            await ctx.send("ℹ️ That message has no embeds.")
            return

        for i, embed in enumerate(message.embeds):
            raw = str(embed.to_dict())
            header = f"**Embed {i + 1}/{len(message.embeds)}**\n"

            # Discord message limit is 2000 chars
            if len(header) + len(raw) + 8 <= 2000:  # +8 for code block markers
                await ctx.send(f"{header}```\n{raw}\n```")
            else:
                # Send as file if too long
                file = discord.File(
                    __import__('io').BytesIO(raw.encode()),
                    filename=f"embed_{i + 1}.txt",
                )
                await ctx.send(header, file=file)

    @commands.command(name='sync')
    @commands.is_owner()
    async def sync_commands(self, ctx: commands.Context, guild_id: int | None = None):
        """Sync slash commands globally or to a specific guild.

        Usage:
          $sync          — global sync (up to 1 hour to propagate)
          $sync <id>     — guild-specific sync (instant)
        """
        try:
            guild = discord.Object(id=guild_id) if guild_id else None
            synced = await self.bot.tree.sync(guild=guild)
            scope = f"guild {guild_id}" if guild_id else "globally"
            await ctx.send(f"✅ Synced {len(synced)} command(s) {scope}.")
        except Exception as e:
            logger.error("Sync failed: %s", e, exc_info=True)
            await ctx.send("❌ Sync failed. Check logs.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
