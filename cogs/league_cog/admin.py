"""
Language League Admin Cog

This module contains all admin-only commands for managing and auditing
the Language League system. All commands require bot owner permissions.
"""
import discord
from discord.ext import commands
from discord import Embed
from base_cog import BaseCog
import logging
from cogs.league_cog.config import (
    LEAGUE_GUILD_ID,
    RATE_LIMITS
)
from cogs.league_cog.utils import (
    detect_message_language,
    CUSTOM_EMOJI_PATTERN,
    UNICODE_EMOJI_PATTERN
)

logger = logging.getLogger(__name__)


class LeagueAdminCog(BaseCog):
    """Admin-only commands for Language League management"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @commands.command(name="league")
    @commands.is_owner()
    async def league_admin(self, ctx, action: str = None, target=None):
        """
        Admin league management (Owner only)

        Available actions:
        - ban <user_id|@user>: Ban user from league
        - unban <user_id|@user>: Unban user from league
        - exclude <#channel>: Exclude channel from league tracking
        - include <#channel>: Re-include excluded channel
        - excluded: List all excluded channels
        - admin_stats: Show league statistics
        - validatemessage <message_link>: Validate message language detection
        - audit <user_id|@user>: Show last 3 counted messages for a user
        """
        if not action:
            await ctx.send(
                "❌ Usage: `$league <ban|unban|exclude|include|excluded|admin_stats|validatemessage|audit> [target]`"
            )
            return

        action = action.lower()

        if action == "ban":
            await self._handle_ban(ctx, target)
        elif action == "unban":
            await self._handle_unban(ctx, target)
        elif action == "exclude":
            await self._handle_exclude(ctx)
        elif action == "include":
            await self._handle_include(ctx)
        elif action == "excluded":
            await self._handle_excluded(ctx)
        elif action == "admin_stats":
            await self._handle_admin_stats(ctx)
        elif action == "validatemessage":
            await self._handle_validate_message(ctx, target)
        elif action == "audit":
            await self._handle_audit(ctx, target)
        else:
            await ctx.send(f"❌ Unknown action: `{action}`")

    async def _handle_ban(self, ctx, target):
        """Ban a user from the league"""
        if not target:
            await ctx.send("❌ Usage: `$league ban <user_id|@user>`")
            return

        try:
            if ctx.message.mentions:
                user_id = ctx.message.mentions[0].id
            else:
                user_id = int(target)

            success = await self.bot.db.leaderboard_ban_user(user_id)
            if success:
                await ctx.send(f"✅ Banned user `{user_id}` from league.")
                logger.info(f"Admin {ctx.author} banned user {user_id} from league")
            else:
                await ctx.send(f"❌ Failed to ban user `{user_id}`.")
        except ValueError:
            await ctx.send("❌ Invalid user ID.")

    async def _handle_unban(self, ctx, target):
        """Unban a user from the league"""
        if not target:
            await ctx.send("❌ Usage: `$league unban <user_id|@user>`")
            return

        try:
            if ctx.message.mentions:
                user_id = ctx.message.mentions[0].id
            else:
                user_id = int(target)

            success = await self.bot.db.leaderboard_unban_user(user_id)
            if success:
                await ctx.send(f"✅ Unbanned user `{user_id}` from league.")
                logger.info(f"Admin {ctx.author} unbanned user {user_id} from league")
            else:
                await ctx.send(f"❌ Failed to unban user `{user_id}`.")
        except ValueError:
            await ctx.send("❌ Invalid user ID.")

    async def _handle_exclude(self, ctx):
        """Exclude a channel from league tracking"""
        if not ctx.message.channel_mentions:
            await ctx.send("❌ Usage: `$league exclude <#channel>`")
            return

        channel = ctx.message.channel_mentions[0]
        success = await self.bot.db.exclude_channel(channel.id, channel.name, ctx.author.id)
        if success:
            await ctx.send(f"✅ Excluded {channel.mention} from league tracking.")
            logger.info(f"Admin {ctx.author} excluded channel {channel.name} ({channel.id}) from league")
        else:
            await ctx.send(f"❌ Failed to exclude {channel.mention}.")

    async def _handle_include(self, ctx):
        """Re-include a channel in league tracking"""
        if not ctx.message.channel_mentions:
            await ctx.send("❌ Usage: `$league include <#channel>`")
            return

        channel = ctx.message.channel_mentions[0]
        success = await self.bot.db.include_channel(channel.id)
        if success:
            await ctx.send(f"✅ Re-included {channel.mention} in league tracking.")
            logger.info(f"Admin {ctx.author} re-included channel {channel.name} ({channel.id}) in league")
        else:
            await ctx.send(f"❌ Channel {channel.mention} was not excluded.")

    async def _handle_excluded(self, ctx):
        """List all excluded channels"""
        channels = await self.bot.db.get_excluded_channels()
        if not channels:
            await ctx.send("ℹ️ No channels are currently excluded.")
            return

        embed = Embed(
            title="🚫 Excluded Channels",
            description=f"Total: {len(channels)} channels",
            color=discord.Color.blue()
        )

        channel_list = []
        for ch in channels[:25]:  # Limit to 25
            channel_list.append(f"<#{ch['channel_id']}> (`{ch['channel_id']}`)")

        embed.add_field(
            name="Channels",
            value="\n".join(channel_list) if channel_list else "None",
            inline=False
        )

        await ctx.send(embed=embed)

    async def _handle_admin_stats(self, ctx):
        """Show league statistics"""
        stats = await self.bot.db.get_league_admin_stats()

        embed = Embed(
            title="📊 Language League - Admin Statistics",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="👥 Participant Breakdown",
            value=(
                f"**Total Active Users:** {stats['total_users']}\n"
                f"🇪🇸 Spanish Learners: {stats['spanish_learners']}\n"
                f"🇬🇧 English Learners: {stats['english_learners']}\n"
                f"🚫 Banned Users: {stats['banned_users']}"
            ),
            inline=False
        )

        embed.add_field(
            name="📈 Activity (Last 30 Days)",
            value=f"**Total Messages Counted:** {stats['total_messages_30d']:,}",
            inline=False
        )

        # Get excluded channels count
        excluded_channels = await self.bot.db.get_excluded_channels()
        embed.add_field(
            name="⚙️ Configuration",
            value=f"**Excluded Channels:** {len(excluded_channels)}",
            inline=False
        )

        await ctx.send(embed=embed)
        logger.info(f"Admin {ctx.author} viewed league statistics")

    async def _handle_validate_message(self, ctx, target):
        """
        Validate message language detection

        Fetches a message from Discord and shows what language would be detected,
        useful for debugging why messages aren't being counted.
        """
        if not target:
            await ctx.send("❌ Usage: `$league validatemessage <message_link>`")
            return

        # Parse message link
        # Format: https://discord.com/channels/guild_id/channel_id/message_id
        try:
            parts = target.rstrip('/').split('/')
            if len(parts) < 3:
                await ctx.send("❌ Invalid message link format")
                return

            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            guild_id = int(parts[-3])

            # Fetch the message
            guild = self.bot.get_guild(guild_id)
            if not guild:
                await ctx.send(f"❌ Could not find guild {guild_id}")
                return

            channel = guild.get_channel(channel_id)
            if not channel:
                await ctx.send(f"❌ Could not find channel {channel_id}")
                return

            message = await channel.fetch_message(message_id)

            # Process message through language detection
            raw_content = message.content
            detected_lang = detect_message_language(raw_content)

            # Remove emojis to show what the detector sees
            content_no_custom = CUSTOM_EMOJI_PATTERN.sub('', raw_content)
            content_clean = UNICODE_EMOJI_PATTERN.sub('', content_no_custom).strip()

            # Build debug embed
            embed = Embed(
                title="🔍 Message Validation",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Author",
                value=f"{message.author.mention} ({message.author.id})",
                inline=False
            )

            embed.add_field(
                name="Raw Content",
                value=f"```\n{raw_content[:1000]}\n```" if raw_content else "*(empty)*",
                inline=False
            )

            embed.add_field(
                name="After Emoji Removal",
                value=f"```\n{content_clean[:1000]}\n```" if content_clean else "*(empty after cleanup)*",
                inline=False
            )

            embed.add_field(
                name="Length Check",
                value=f"Raw: {len(raw_content)} chars | Clean: {len(content_clean)} chars | Min required: {RATE_LIMITS.MIN_MESSAGE_LENGTH}",
                inline=False
            )

            result_emoji = "✅" if detected_lang else "❌"
            result_text = f"{result_emoji} **{detected_lang.upper()}**" if detected_lang else "❌ **Not detected** (too short or no valid language)"

            embed.add_field(
                name="Detected Language",
                value=result_text,
                inline=False
            )

            embed.add_field(
                name="Would Count?",
                value="✅ Yes (if user opted in, not on cooldown, etc.)" if detected_lang else "❌ No (language detection failed)",
                inline=False
            )

            embed.set_footer(text=f"Message ID: {message_id}")

            await ctx.send(embed=embed)
            logger.info(f"Admin {ctx.author} validated message {message_id}")

        except ValueError:
            await ctx.send("❌ Invalid message link format (IDs must be numbers)")
        except discord.NotFound:
            await ctx.send("❌ Message not found")
        except discord.Forbidden:
            await ctx.send("❌ No permission to access that message")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            logger.error(f"Error in validatemessage: {e}", exc_info=True)

    async def _handle_audit(self, ctx, target):
        """
        Audit a user's counted messages

        Shows the last 3 messages that were counted for a specific user,
        including their content and detected language. Useful for verifying
        the bot is counting messages correctly.
        """
        if not target:
            await ctx.send("❌ Usage: `$league audit <user_id|@user>`")
            return

        try:
            # Get user ID
            if ctx.message.mentions:
                user_id = ctx.message.mentions[0].id
            else:
                user_id = int(target)

            # Check if user is in the league
            is_opted_in = await self.bot.db.is_user_opted_in(user_id)
            if not is_opted_in:
                await ctx.send(f"❌ User `{user_id}` is not in the league.")
                return

            # Get last 3 counted messages from database
            async with self.bot.db.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT message_id, channel_id, points, created_at, round_id
                    FROM leaderboard_activity
                    WHERE user_id = $1 AND message_id IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 3
                ''', user_id)

            if not rows:
                await ctx.send(f"ℹ️ No counted messages found for user `{user_id}`.")
                return

            # Fetch actual message content from Discord
            guild = self.bot.get_guild(LEAGUE_GUILD_ID)
            if not guild:
                await ctx.send("❌ Could not find league guild.")
                return

            embed = Embed(
                title=f"🔍 League Audit - User {user_id}",
                description="Last 3 counted messages",
                color=discord.Color.blue()
            )

            for i, row in enumerate(rows, 1):
                try:
                    channel = guild.get_channel(row['channel_id'])
                    if not channel:
                        embed.add_field(
                            name=f"Message {i}",
                            value=f"❌ Channel not found (ID: {row['channel_id']})",
                            inline=False
                        )
                        continue

                    message = await channel.fetch_message(row['message_id'])

                    # Truncate if too long
                    content = message.content[:500] + "..." if len(message.content) > 500 else message.content

                    # Detect language for verification
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
                        inline=False
                    )

                except discord.NotFound:
                    embed.add_field(
                        name=f"Message {i}",
                        value=f"❌ Message deleted or not found (ID: {row['message_id']})",
                        inline=False
                    )
                except discord.Forbidden:
                    embed.add_field(
                        name=f"Message {i}",
                        value="❌ No permission to access message",
                        inline=False
                    )
                except Exception as e:
                    embed.add_field(
                        name=f"Message {i}",
                        value=f"❌ Error: {str(e)}",
                        inline=False
                    )

            await ctx.send(embed=embed)
            logger.info(f"Admin {ctx.author} audited user {user_id}")

        except ValueError:
            await ctx.send("❌ Invalid user ID.")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            logger.error(f"Error in audit command: {e}", exc_info=True)


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(LeagueAdminCog(bot))
    logger.info("LeagueAdminCog loaded successfully")
