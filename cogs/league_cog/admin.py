"""
Language League Admin Cog

This module contains all admin-only commands for managing and auditing
the Language League system. All commands require bot owner permissions.
"""
import asyncio
import logging
import re
import time

import discord
from discord import Embed
from discord.ext import commands

from base_cog import BaseCog
from cogs.league_cog.config import LEAGUE_GUILD_ID, RATE_LIMITS
from cogs.league_cog.rounds import (
    build_round_end_announcement,
    get_eligible_champions,
)
from cogs.league_cog.utils import (
    CUSTOM_EMOJI_PATTERN,
    UNICODE_EMOJI_PATTERN,
    detect_message_language,
)
from cogs.league_cog.views import LeagueJoinView

logger = logging.getLogger(__name__)


class LeagueAdminCog(BaseCog):
    """Admin-only commands for Language League management"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @commands.group(name="league", invoke_without_command=True)
    @commands.is_owner()
    async def league_admin(self, ctx: commands.Context):
        """🏆 Language League — Compete with other learners!

Earn points by chatting in your target language channels. The more active you are, the higher you climb!

**How to join:** Use `/league join` (you need a native + learning role)
**View rankings:** `/league view`
**Your stats:** `/league stats`
**Leave:** `/league leave`

Rounds last 2 weeks. Top performers earn a champion role!"""
        await ctx.send(
            "❌ Usage: `$league <ban|unban|exclude|include|excluded|admin_stats|validatemessage|audit|endround|seedrole|preview|reminder|recent|topchannels|heatmap> [target]`"
        )

    @league_admin.command(name="topchannels", aliases=["topchans"])
    @commands.is_owner()
    async def topchannels(self, ctx: commands.Context, days: int = 30):
        """Show channels that produced the most counted league messages.

        Usage: `$league topchannels [days]` (default 30, 1–365)
        """
        days = max(1, min(days, 365))
        rows = await self.bot.db.get_top_activity_channels(days=days, limit=15)

        if not rows:
            return await ctx.send(
                f"ℹ️ No counted activity in the last {days} day(s)."
            )

        excluded_ids = {
            r['channel_id']
            for r in await self.bot.db.get_excluded_channels()
        }

        # Resolve human-friendly channel labels. Uncached / deleted
        # channels fall back to "#<id>" so the chart still renders.
        channel_labels: dict[int, str] = {}
        for r in rows:
            cid = r['channel_id']
            ch = ctx.guild.get_channel(cid) if ctx.guild else None
            channel_labels[cid] = f"#{ch.name}" if ch else f"#{cid}"

        # Lazy import + offload rendering off the event loop.
        from cogs.league_cog.league_helper.topchannels_image import (
            render_top_channels,
        )
        buf = await asyncio.to_thread(
            render_top_channels,
            list(rows),
            channel_labels=channel_labels,
            excluded_ids=excluded_ids,
            days=days,
        )
        file = discord.File(buf, filename="league_topchannels.png")

        embed = Embed(
            title=f"📊 Top League Channels (last {days}d)",
            color=discord.Color.blue(),
        )
        embed.set_image(url="attachment://league_topchannels.png")
        embed.set_footer(text="🔴 red bars = currently excluded from tracking")
        await ctx.send(
            embed=embed, file=file,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        logger.info(
            "Admin %s viewed topchannels (%dd, %d rows)",
            ctx.author, days, len(rows),
        )

    @league_admin.command(name="heatmap", aliases=["hm"])
    @commands.is_owner()
    async def heatmap(self, ctx: commands.Context, days: int = 30):
        """Show a 7×24 activity heatmap (day-of-week × hour) over a window.

        Usage: `$league heatmap [days]` (default 30, 1–365)
        """
        days = max(1, min(days, 365))
        rows = await self.bot.db.get_activity_heatmap(days=days)

        # Build 7x24 grid. Postgres DOW: 0=Sunday … 6=Saturday.
        # The renderer handles Mon-first reordering itself.
        grid = [[0] * 24 for _ in range(7)]
        for r in rows:
            grid[r['dow']][r['hour']] = r['cnt']

        peak = max((max(row) for row in grid), default=0)
        if peak == 0:
            return await ctx.send(
                f"ℹ️ No counted activity in the last {days} day(s)."
            )

        # Lazy import so matplotlib/seaborn load only when this command
        # is actually invoked, not at bot startup.
        from cogs.league_cog.league_helper.heatmap_image import render_heatmap

        # Rendering is CPU-bound (~200-400 ms) — push it off the event
        # loop so we don't stall other cogs' message handlers.
        buf = await asyncio.to_thread(
            render_heatmap, grid, days=days, peak=peak,
        )
        file = discord.File(buf, filename="league_heatmap.png")

        embed = Embed(
            title=f"🔥 League Activity Heatmap (last {days}d)",
            color=discord.Color.blue(),
        )
        embed.set_image(url="attachment://league_heatmap.png")
        embed.set_footer(text="Times are UTC · hours across, weekdays down")
        await ctx.send(embed=embed, file=file)
        logger.info(
            "Admin %s viewed heatmap (%dd, peak=%d)", ctx.author, days, peak,
        )

    @league_admin.command(name="recent", aliases=["joiners", "joins"])
    @commands.is_owner()
    async def recent(self, ctx: commands.Context, limit: int = 10):
        """Show the most recent first-time league joiners. Usage: `$league recent [limit]`"""
        limit = max(1, min(limit, 25))
        rows = await self.bot.db.get_recent_joiners(limit)

        if not rows:
            return await ctx.send("ℹ️ No league joiners recorded yet.")

        lines: list[str] = []
        for i, row in enumerate(rows, 1):
            if row['learning_spanish']:
                flag = "🇪🇸"
            elif row['learning_english']:
                flag = "🇬🇧"
            else:
                flag = "❓"
            status = "" if row['opted_in'] else " · *left*"
            joined_ts = int(row['joined_at'].timestamp())
            lines.append(
                f"**{i}.** {flag} <@{row['user_id']}> (`{row['username']}`) "
                f"· <t:{joined_ts}:R>{status}"
            )

        embed = Embed(
            title=f"🆕 Recent League Joiners (last {len(rows)})",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Ordered by first-time join timestamp. Banned users hidden.")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        logger.info("Admin %s viewed last %d league joiners", ctx.author, len(rows))

    @league_admin.command(name="reminder")
    @commands.is_owner()
    async def reminder(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        """Post a public “Join the League” reminder embed with a persistent button.

        Usage: `$league reminder [#channel]` — defaults to the current channel.
        """
        if ctx.guild is None or ctx.guild.id != LEAGUE_GUILD_ID:
            return await ctx.send("❌ This command can only be used in the league guild.")

        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel) or target.guild.id != LEAGUE_GUILD_ID:
            return await ctx.send("❌ Target channel must be a text channel in the league guild.")

        embed = Embed(
            title="🏆 Join the Language League!",
            description=(
                "Chat in Spanish or English, earn points, win a champion role.\n\n"
                "Click below to join. Requires a native role + a learning role."
            ),
            color=discord.Color.gold(),
        )

        try:
            await target.send(embed=embed, view=LeagueJoinView(self.bot))
        except discord.Forbidden:
            return await ctx.send(f"❌ I don't have permission to post in {target.mention}.")
        except discord.HTTPException:
            logger.exception("Failed to send league reminder in %s", target.id)
            return await ctx.send("❌ Failed to send reminder. Check logs.")

        if target.id != ctx.channel.id:
            await ctx.send(f"✅ Reminder posted in {target.mention}.")
        logger.info("Admin %s posted league reminder in #%s (%s)", ctx.author, target.name, target.id)

    @league_admin.command(name="ban")
    @commands.is_owner()
    async def ban(self, ctx: commands.Context, target: str | None = None):
        """Ban a user from the league. Usage: `$league ban <user_id|@user>`"""
        if not target:
            return await ctx.send("❌ Usage: `$league ban <user_id|@user>`")

        try:
            user_id = ctx.message.mentions[0].id if ctx.message.mentions else int(target)
            success = await self.bot.db.leaderboard_ban_user(user_id)
            if success:
                league_cog = self.bot.get_cog("LeagueCog")
                if league_cog:
                    league_cog._banned_users.add(user_id)
                await ctx.send(f"✅ Banned user `{user_id}` from league.")
                logger.info("Admin %s banned user %s from league", ctx.author, user_id)
            else:
                await ctx.send(f"❌ Failed to ban user `{user_id}`.")
        except ValueError:
            await ctx.send("❌ Invalid user ID.")

    @league_admin.command(name="unban")
    @commands.is_owner()
    async def unban(self, ctx: commands.Context, target: str | None = None):
        """Unban a user from the league. Usage: `$league unban <user_id|@user>`"""
        if not target:
            return await ctx.send("❌ Usage: `$league unban <user_id|@user>`")

        try:
            user_id = ctx.message.mentions[0].id if ctx.message.mentions else int(target)
            success = await self.bot.db.leaderboard_unban_user(user_id)
            if success:
                league_cog = self.bot.get_cog("LeagueCog")
                if league_cog:
                    league_cog._banned_users.discard(user_id)
                await ctx.send(f"✅ Unbanned user `{user_id}` from league.")
                logger.info("Admin %s unbanned user %s from league", ctx.author, user_id)
            else:
                await ctx.send(f"❌ Failed to unban user `{user_id}`.")
        except ValueError:
            await ctx.send("❌ Invalid user ID.")

    @league_admin.command(name="exclude")
    @commands.is_owner()
    async def exclude(self, ctx: commands.Context):
        """Exclude a channel from league tracking. Usage: `$league exclude <#channel>`"""
        if not ctx.message.channel_mentions:
            return await ctx.send("❌ Usage: `$league exclude <#channel>`")

        channel = ctx.message.channel_mentions[0]
        success = await self.bot.db.exclude_channel(channel.id, channel.name, ctx.author.id)
        if success:
            league_cog = self.bot.get_cog("LeagueCog")
            if league_cog:
                league_cog._excluded_channels.add(channel.id)
            await ctx.send(f"✅ Excluded {channel.mention} from league tracking.")
            logger.info("Admin %s excluded channel %s (%s) from league", ctx.author, channel.name, channel.id)
        else:
            await ctx.send(f"❌ Failed to exclude {channel.mention}.")

    @league_admin.command(name="include")
    @commands.is_owner()
    async def include(self, ctx: commands.Context):
        """Re-include a channel in league tracking. Usage: `$league include <#channel>`"""
        if not ctx.message.channel_mentions:
            return await ctx.send("❌ Usage: `$league include <#channel>`")

        channel = ctx.message.channel_mentions[0]
        success = await self.bot.db.include_channel(channel.id)
        if success:
            league_cog = self.bot.get_cog("LeagueCog")
            if league_cog:
                league_cog._excluded_channels.discard(channel.id)
            await ctx.send(f"✅ Re-included {channel.mention} in league tracking.")
            logger.info("Admin %s re-included channel %s (%s) in league", ctx.author, channel.name, channel.id)
        else:
            await ctx.send(f"❌ Channel {channel.mention} was not excluded.")

    @league_admin.command(name="excluded")
    @commands.is_owner()
    async def excluded(self, ctx: commands.Context):
        """List all excluded channels."""
        channels = await self.bot.db.get_excluded_channels()
        if not channels:
            return await ctx.send("ℹ️ No channels are currently excluded.")

        embed = Embed(
            title="🚫 Excluded Channels",
            description=f"Total: {len(channels)} channels",
            color=discord.Color.blue(),
        )
        channel_list = [f"<#{ch['channel_id']}> (`{ch['channel_id']}`)" for ch in channels[:25]]
        embed.add_field(name="Channels", value="\n".join(channel_list), inline=False)
        await ctx.send(embed=embed)

    @league_admin.command(name="admin_stats")
    @commands.is_owner()
    async def admin_stats(self, ctx: commands.Context):
        """Show league statistics."""
        stats = await self.bot.db.get_league_admin_stats()

        embed = Embed(title="📊 Language League - Admin Statistics", color=discord.Color.blue())
        embed.add_field(
            name="👥 Participant Breakdown",
            value=(
                f"**Total Active Users:** {stats['total_users']}\n"
                f"🇪🇸 Spanish Learners: {stats['spanish_learners']}\n"
                f"🇬🇧 English Learners: {stats['english_learners']}\n"
                f"🚫 Banned Users: {stats['banned_users']}"
            ),
            inline=False,
        )
        embed.add_field(
            name="📈 Activity (Last 30 Days)",
            value=f"**Total Messages Counted:** {stats['total_messages_30d']:,}",
            inline=False,
        )
        excluded_channels = await self.bot.db.get_excluded_channels()
        embed.add_field(
            name="⚙️ Configuration",
            value=f"**Excluded Channels:** {len(excluded_channels)}",
            inline=False,
        )
        await ctx.send(embed=embed)
        logger.info("Admin %s viewed league statistics", ctx.author)

    @league_admin.command(name="validatemessage")
    @commands.is_owner()
    async def validatemessage(self, ctx: commands.Context, target: str | None = None):
        """Validate message language detection. Usage: `$league validatemessage <message_link>`"""
        if not target:
            return await ctx.send("❌ Usage: `$league validatemessage <message_link>`")

        try:
            parts = target.rstrip('/').split('/')
            if len(parts) < 3:
                return await ctx.send("❌ Invalid message link format")

            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            guild_id = int(parts[-3])

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return await ctx.send(f"❌ Could not find guild {guild_id}")

            channel = guild.get_channel(channel_id)
            if not channel:
                return await ctx.send(f"❌ Could not find channel {channel_id}")

            message = await channel.fetch_message(message_id)

            raw_content = message.content
            detected_lang = detect_message_language(raw_content)

            content_no_custom = CUSTOM_EMOJI_PATTERN.sub('', raw_content)
            content_clean = UNICODE_EMOJI_PATTERN.sub('', content_no_custom).strip()

            embed = Embed(title="🔍 Message Validation", color=discord.Color.blue())
            embed.add_field(name="Author", value=f"{message.author.mention} ({message.author.id})", inline=False)
            embed.add_field(
                name="Raw Content",
                value=f"```\n{raw_content[:1000]}\n```" if raw_content else "*(empty)*",
                inline=False,
            )
            embed.add_field(
                name="After Emoji Removal",
                value=f"```\n{content_clean[:1000]}\n```" if content_clean else "*(empty after cleanup)*",
                inline=False,
            )
            embed.add_field(
                name="Length Check",
                value=f"Raw: {len(raw_content)} chars | Clean: {len(content_clean)} chars | Min required: {RATE_LIMITS.MIN_MESSAGE_LENGTH}",
                inline=False,
            )

            result_text = (
                f"✅ **{detected_lang.upper()}**" if detected_lang
                else "❌ **Not detected** (too short or no valid language)"
            )
            embed.add_field(name="Detected Language", value=result_text, inline=False)
            embed.add_field(
                name="Would Count?",
                value="✅ Yes (if user opted in, not on cooldown, etc.)" if detected_lang else "❌ No (language detection failed)",
                inline=False,
            )
            embed.set_footer(text=f"Message ID: {message_id}")
            await ctx.send(embed=embed)
            logger.info("Admin %s validated message %s", ctx.author, message_id)

        except ValueError:
            await ctx.send("❌ Invalid message link format (IDs must be numbers)")
        except discord.NotFound:
            await ctx.send("❌ Message not found")
        except discord.Forbidden:
            await ctx.send("❌ No permission to access that message")
        except Exception as e:
            await ctx.send("❌ Something went wrong. Check logs.")
            logger.error("Error in validatemessage: %s", e, exc_info=True)

    @league_admin.command(name="audit")
    @commands.is_owner()
    async def audit(self, ctx: commands.Context, target: str | None = None):
        """Audit a user's last 3 counted messages. Usage: `$league audit <user_id|@user>`"""
        if not target:
            return await ctx.send("❌ Usage: `$league audit <user_id|@user>`")

        try:
            user_id = ctx.message.mentions[0].id if ctx.message.mentions else int(target)

            is_opted_in = await self.bot.db.is_user_opted_in(user_id)
            if not is_opted_in:
                return await ctx.send(f"❌ User `{user_id}` is not in the league.")

            rows = await self.bot.db.get_recent_user_activity(user_id)
            if not rows:
                return await ctx.send(f"ℹ️ No counted messages found for user `{user_id}`.")

            guild = self.bot.get_guild(LEAGUE_GUILD_ID)
            if not guild:
                return await ctx.send("❌ Could not find league guild.")

            embed = Embed(
                title=f"🔍 League Audit - User {user_id}",
                description="Last 3 counted messages",
                color=discord.Color.blue(),
            )

            for i, row in enumerate(rows, 1):
                try:
                    channel = guild.get_channel(row['channel_id'])
                    if not channel:
                        embed.add_field(
                            name=f"Message {i}",
                            value=f"❌ Channel not found (ID: {row['channel_id']})",
                            inline=False,
                        )
                        continue

                    message = await channel.fetch_message(row['message_id'])
                    content = message.content[:500] + "..." if len(message.content) > 500 else message.content
                    detected_lang = detect_message_language(message.content)
                    lang_display = f"**Detected:** {detected_lang.upper()}" if detected_lang else "**Detected:** None ❌"

                    embed.add_field(
                        name=f"Message {i} - #{channel.name}",
                        value=(
                            f"```\n{content}\n```\n"
                            f"{lang_display}\n"
                            f"**Points:** {row['points']} | **Round:** {row['round_id']}\n"
                            f"**Date:** {row['created_at'].strftime('%Y-%m-%d %H:%M UTC')}\n"
                            f"[Jump to message](https://discord.com/channels/{guild.id}/{row['channel_id']}/{row['message_id']})"
                        ),
                        inline=False,
                    )
                except discord.NotFound:
                    embed.add_field(name=f"Message {i}", value=f"❌ Message deleted or not found (ID: {row['message_id']})", inline=False)
                except discord.Forbidden:
                    embed.add_field(name=f"Message {i}", value="❌ No permission to access message", inline=False)
                except Exception as e:
                    logger.error("Error fetching audit message: %s", e, exc_info=True)
                    embed.add_field(name=f"Message {i}", value="❌ Failed to fetch message", inline=False)

            await ctx.send(embed=embed)
            logger.info("Admin %s audited user %s", ctx.author, user_id)

        except ValueError:
            await ctx.send("❌ Invalid user ID.")
        except Exception as e:
            await ctx.send("❌ Something went wrong. Check logs.")
            logger.error("Error in audit command: %s", e, exc_info=True)

    @league_admin.command(name="endround")
    @commands.is_owner()
    async def endround(self, ctx: commands.Context):
        """End current round and start a new one."""
        try:
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                return await ctx.send("❌ No active round found.")

            round_number = current_round['round_number']
            await ctx.send(f"⏳ Ending round {round_number}...")

            league_cog = self.bot.get_cog('LeagueCog')
            if not league_cog:
                return await ctx.send("❌ LeagueCog not loaded.")

            result = await league_cog._process_round_end(current_round)

            end_timestamp = int(result['next_end'].timestamp())
            embed = Embed(
                title="✅ Round Ended Successfully",
                description=f"Round {result['round_number']} has been ended.",
                color=discord.Color.green(),
            )
            embed.add_field(name="New Round", value=f"**Round {result['next_round_number']}** has started!", inline=False)
            embed.add_field(name="Ends", value=f"<t:{end_timestamp}:F> (<t:{end_timestamp}:R>)", inline=False)
            embed.add_field(name="Winners Saved", value=f"Spanish: {len(result['spanish_top3'])} | English: {len(result['english_top3'])}", inline=False)
            embed.add_field(name="Champion Role", value=f"Added: {len(result['roles_added'])} | Removed: {len(result['roles_removed'])}", inline=False)
            await ctx.send(embed=embed)
            logger.info("Admin %s manually ended round %s, created round %s", ctx.author, round_number, result['next_round_number'])

        except Exception as e:
            await ctx.send("❌ Error ending round. Check logs.")
            logger.error("Error in endround command: %s", e, exc_info=True)

    @league_admin.command(name="seedrole")
    @commands.is_owner()
    async def seedrole(self, ctx: commands.Context, target: str | None = None):
        """Seed last round's role recipients. Usage: `$league seedrole <id1,id2,...>`"""
        if not target:
            return await ctx.send("❌ Usage: `$league seedrole <user_id1,user_id2,...>`")

        try:
            user_ids = [int(uid.strip()) for uid in target.split(',')]
            await self.bot.db.seed_role_recipients(user_ids)
            await ctx.send(f"✅ Seeded {len(user_ids)} users as last round's role recipients:\n{', '.join(str(uid) for uid in user_ids)}")
            logger.info("Admin %s seeded role recipients: %s", ctx.author, user_ids)
        except ValueError:
            await ctx.send("❌ Invalid format. Use comma-separated user IDs: `$league seedrole 123,456,789`")
        except Exception as e:
            await ctx.send("❌ Something went wrong. Check logs.")
            logger.error("Error in seedrole command: %s", e, exc_info=True)

    @league_admin.command(name="preview")
    @commands.is_owner()
    async def preview(self, ctx: commands.Context):
        """Preview round-end announcement without making changes."""
        try:
            current_round = await self.bot.db.get_current_round()
            if not current_round:
                return await ctx.send("❌ No active round found.")

            league_cog = self.bot.get_cog('LeagueCog')
            if not league_cog:
                return await ctx.send("❌ LeagueCog not loaded.")

            round_id = current_round['round_id']
            round_number = current_round['round_number']

            last_round_recipients = await self.bot.db.get_last_round_role_recipients()
            spanish_top = await self.bot.db.get_leaderboard('spanish', limit=10, round_id=round_id)
            english_top = await self.bot.db.get_leaderboard('english', limit=10, round_id=round_id)

            spanish_top3 = spanish_top[:3]
            english_top3 = english_top[:3]
            spanish_champions = get_eligible_champions(spanish_top, last_round_recipients)
            english_champions = get_eligible_champions(english_top, last_round_recipients)

            message = build_round_end_announcement(
                round_number=round_number,
                spanish_top3=spanish_top3,
                english_top3=english_top3,
                spanish_champions=spanish_champions,
                english_champions=english_champions,
                last_round_recipients=last_round_recipients,
            )

            preview_header = "*— PREVIEW MODE (no pings, no changes) —*\n\n"
            preview_footer = ""
            if last_round_recipients:
                preview_footer = f"\n\n---\n**ℹ️ On Cooldown (from last round):** {', '.join(f'<@{uid}>' for uid in last_round_recipients)}"

            await ctx.send(preview_header + message + preview_footer)
            logger.info("Admin %s previewed round %s announcement", ctx.author, round_number)

        except Exception as e:
            await ctx.send("❌ Something went wrong. Check logs.")
            logger.error("Error in preview command: %s", e, exc_info=True)

    @commands.command(name="langa", aliases=["lng"])
    @commands.is_owner()
    async def langa(self, ctx: commands.Context, *, message_or_id: str | None = None):
        """
        Detect the language of a message (Owner only)

        Usage:
        - $langa <text>: Detect language of provided text
        - $langa <message_link>: Fetch message by Discord link and detect its language
        """
        if not message_or_id:
            return await ctx.send("❌ Usage: `$langa <text or message link>`")

        stripped = message_or_id.strip()
        content = None
        source_label = None

        if 'discord.com/channels/' in stripped:
            try:
                parts = stripped.rstrip('/').split('/')
                message_id = int(parts[-1])
                channel_id = int(parts[-2])
                guild_id = int(parts[-3])

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return await ctx.send(f"❌ Could not find guild `{guild_id}`.")

                channel = guild.get_channel(channel_id)
                if not channel:
                    return await ctx.send(f"❌ Could not find channel `{channel_id}`.")

                message = await channel.fetch_message(message_id)
                content = message.content
                source_label = f"Message by {message.author.mention} in #{channel.name}"
            except (ValueError, IndexError):
                return await ctx.send("❌ Invalid message link format.")
            except discord.NotFound:
                return await ctx.send("❌ Message not found.")
            except discord.Forbidden:
                return await ctx.send("❌ No permission to fetch that message.")
            except Exception as e:
                logger.error("Error fetching message in langa: %s", e, exc_info=True)
                return await ctx.send("❌ Failed to fetch message.")
        else:
            content = stripped
            source_label = "Provided text"

        if not content:
            return await ctx.send("❌ Message has no text content.")

        mention_pattern = re.compile(r'<@!?\d+>|<@&\d+>|<#\d+>')
        content_no_mentions = mention_pattern.sub('', content)
        content_no_custom = CUSTOM_EMOJI_PATTERN.sub('', content_no_mentions)
        content_clean = UNICODE_EMOJI_PATTERN.sub('', content_no_custom).strip()

        start = time.perf_counter()
        detected = detect_message_language(content_no_mentions)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if detected == 'es':
            lang_display = "🇪🇸 Spanish"
        elif detected == 'en':
            lang_display = "🇬🇧 English"
        else:
            lang_display = "❓ Neither / Unknown"

        embed = Embed(title="🔎 Language Detection", color=discord.Color.blue())
        embed.add_field(name="Source", value=source_label, inline=False)
        embed.add_field(name="Language", value=lang_display, inline=True)
        embed.add_field(name="Characters", value=f"Raw: {len(content)} | Clean: {len(content_clean)}", inline=True)
        embed.add_field(name="Time", value=f"{elapsed_ms:.2f}ms", inline=True)

        await ctx.send(embed=embed)
        logger.info("Admin %s ran langa on %s-char message → %s", ctx.author, len(content), detected)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(LeagueAdminCog(bot))
    logger.info("LeagueAdminCog loaded successfully")
