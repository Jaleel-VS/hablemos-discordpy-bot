"""
Language League Admin Cog

This module contains all admin-only commands for managing and auditing
the Language League system. All commands require bot owner permissions.
"""
import logging
import re
import time

import discord
from discord import Embed
from discord.ext import commands

from base_cog import BaseCog
from cogs.league_cog.config import LEAGUE_GUILD_ID, RATE_LIMITS
from cogs.league_cog.utils import (
    CUSTOM_EMOJI_PATTERN,
    UNICODE_EMOJI_PATTERN,
    detect_message_language,
)

logger = logging.getLogger(__name__)


class LeagueAdminCog(BaseCog):
    """Admin-only commands for Language League management"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @commands.group(name="league", invoke_without_command=True)
    @commands.is_owner()
    async def league_admin(self, ctx: commands.Context):
        """Admin league management (Owner only). Use `$league <subcommand>`."""
        await ctx.send(
            "❌ Usage: `$league <ban|unban|exclude|include|excluded|admin_stats|validatemessage|audit|endround|seedrole|preview> [target]`"
        )

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
            await ctx.send(f"❌ Error: {e!s}")
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
                    embed.add_field(name=f"Message {i}", value=f"❌ Error: {e!s}", inline=False)

            await ctx.send(embed=embed)
            logger.info("Admin %s audited user %s", ctx.author, user_id)

        except ValueError:
            await ctx.send("❌ Invalid user ID.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e!s}")
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

            result = await league_cog.process_round_end(current_round)

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
            await ctx.send(f"❌ Error ending round: {e!s}")
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
            await ctx.send(f"❌ Error: {e!s}")
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
            spanish_champions = league_cog.get_eligible_champions(spanish_top, last_round_recipients)
            english_champions = league_cog.get_eligible_champions(english_top, last_round_recipients)

            message = league_cog.build_round_end_announcement(
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
            await ctx.send(f"❌ Error: {e!s}")
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
                return await ctx.send(f"❌ Error fetching message: {e}")
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
