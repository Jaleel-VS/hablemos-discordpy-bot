"""
Conversation Summary Cog for Discord using Google Gemini AI
"""
import logging
import discord
from discord.ext import commands
from base_cog import BaseCog, COLORS
from .gemini_client import GeminiClient
from .cache import SummaryCache
from .message_parser import parse_message_link
import random

logger = logging.getLogger(__name__)


class SummaryCog(BaseCog):
    """Cog for AI-powered conversation summaries using Gemini"""

    def __init__(self, bot):
        super().__init__(bot)
        try:
            self.gemini = GeminiClient()
            self.cache = SummaryCache(ttl_seconds=3600)  # 1 hour cache
            logger.info("SummaryCog initialized successfully")
        except ValueError as e:
            logger.error(f"Failed to initialize SummaryCog: {e}")
            raise

    @commands.command(name='summarize', aliases=['summary', 'sum'])
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def summarize(self, ctx, message_link: str, count: int = 100):
        """
        Summarize conversation from a Discord message link

        This command uses AI to summarize conversations starting from a specific message.
        Restricted to moderators for moderation purposes.

        Usage:
            $summarize https://discord.com/channels/.../... [count]
            $sum https://discord.com/channels/.../... 50

        Args:
            message_link: Discord message link (right-click message > Copy Message Link)
            count: Number of messages to analyze after the linked message (default: 100, max: 500)
        """
        # Validate count parameter
        if count < 1:
            await ctx.send("❌ Message count must be at least 1.")
            return
        if count > 500:
            await ctx.send("❌ Maximum message count is 500.")
            return

        # Parse the message link
        guild_id, channel_id, message_id = parse_message_link(message_link)

        if not all([guild_id, channel_id, message_id]):
            await ctx.send("❌ Invalid message link. Use: `https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID`\n\nTo get a message link: Right-click a message > Copy Message Link")
            return

        # Validate guild matches
        if ctx.guild.id != guild_id:
            await ctx.send("❌ That message is from a different server.")
            return

        # Send processing message
        processing_msg = await ctx.send(f"🔍 Analyzing {count} messages... This may take a moment.")

        try:
            # Get the channel
            channel = self.bot.get_channel(channel_id)
            if not channel:
                await processing_msg.edit(content="❌ I can't access that channel.")
                return

            # Check cache first
            cached_summary = self.cache.get_summary(channel_id, message_id, count)
            from_cache = cached_summary is not None

            if not from_cache:
                # Fetch the starting message
                try:
                    starting_message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    await processing_msg.edit(content="❌ Message not found. It may have been deleted.")
                    return
                except discord.Forbidden:
                    await processing_msg.edit(content="❌ I don't have permission to access that channel.")
                    return

                # Fetch messages after the starting message
                messages = []
                async for message in channel.history(limit=count, after=starting_message, oldest_first=True):
                    # Skip bot messages
                    if not message.author.bot:
                        messages.append({
                            'author': message.author.display_name,
                            'content': message.content,
                            'timestamp': message.created_at
                        })

                # Check if we found any messages
                if not messages:
                    await processing_msg.edit(content="❌ No user messages found after the specified message.")
                    return

                # Update processing message
                await processing_msg.edit(content=f"✨ Generating AI summary for {len(messages)} messages...")

                # Generate summary with Gemini
                try:
                    summary_text = self.gemini.generate_summary(messages)
                except Exception as e:
                    logger.error(f"Gemini API error: {e}", exc_info=True)
                    error_msg = "❌ Failed to generate summary. "

                    # Check for specific error types
                    error_str = str(e).lower()
                    if "rate" in error_str or "quota" in error_str or "429" in error_str:
                        error_msg += "API rate limit reached. Please try again in a few minutes."
                    elif "timeout" in error_str:
                        error_msg += "Request timed out. Please try again."
                    elif "safety" in error_str or "blocked" in error_str:
                        error_msg += "Summary could not be generated due to content policy."
                    else:
                        error_msg += "Please try again later."

                    await processing_msg.edit(content=error_msg)
                    return

                # Cache the result
                self.cache.set_summary(channel_id, message_id, count, summary_text)
                cached_summary = summary_text

                # Store message timestamps for time range
                start_time = messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M')
                end_time = messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M')
                actual_count = len(messages)
            else:
                # Using cached summary - we don't have the original messages
                start_time = "Cached"
                end_time = "Cached"
                actual_count = count

            # Create embed with summary
            embed = discord.Embed(
                title="📝 Conversation Summary",
                description=cached_summary[:4000],  # Discord description limit
                color=random.choice(COLORS)
            )

            # Add metadata fields
            embed.add_field(name="Messages Analyzed", value=str(actual_count), inline=True)

            if not from_cache:
                embed.add_field(name="Time Range", value=f"{start_time}\nto\n{end_time}", inline=True)

            # Footer with attribution and cache status
            footer_text = "AI-generated summary • For moderation purposes"
            if from_cache:
                footer_text += " • 💾 From cache"
            embed.set_footer(text=footer_text)

            # Edit the processing message with the result
            await processing_msg.edit(content=f"{ctx.author.mention}", embed=embed)

        except discord.Forbidden:
            await processing_msg.edit(content="❌ I don't have permission to access that channel.")
        except Exception as e:
            logger.error(f"Unexpected error in summarize command: {e}", exc_info=True)
            await processing_msg.edit(content="❌ An unexpected error occurred. Please try again later.")

    @commands.command(name='summary_stats', aliases=['sum_stats'])
    @commands.is_owner()
    async def summary_stats(self, ctx):
        """Show summary cache statistics (bot owner only)"""
        stats = self.cache.get_stats()

        embed = discord.Embed(
            title="📊 Summary Cache Statistics",
            color=0x3498db
        )

        embed.add_field(
            name="Cache Usage",
            value=f"""
            **Size:** {stats['size']} entries
            **Total Requests:** {stats['total_requests']}
            **Hits:** {stats['hits']} ({stats['hit_rate']:.1f}%)
            **Misses:** {stats['misses']}
            """,
            inline=False
        )

        embed.add_field(
            name="Operations",
            value=f"""
            **Stored:** {stats['stores']}
            **Evictions:** {stats['evictions']}
            """,
            inline=False
        )

        # Calculate efficiency message
        if stats['hit_rate'] >= 50:
            efficiency = "🟢 Excellent"
        elif stats['hit_rate'] >= 30:
            efficiency = "🟡 Good"
        else:
            efficiency = "🟠 Normal"

        embed.add_field(
            name="Efficiency",
            value=efficiency,
            inline=False
        )

        embed.set_footer(text="TTL: 1 hour")
        await ctx.send(embed=embed)

    @commands.command(name='clear_summary_cache', aliases=['sum_clear'])
    @commands.is_owner()
    async def clear_cache(self, ctx):
        """Clear the summary cache (bot owner only)"""
        count = self.cache.clear()
        await ctx.send(f"✅ Summary cache cleared. Removed {count} entries.")

    async def cog_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need moderator permissions (Manage Messages) to use this command.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ Command on cooldown. Try again in {error.retry_after:.1f} seconds.")
        elif isinstance(error, discord.NotFound):
            await ctx.send("❌ Message not found. It may have been deleted.")
        elif isinstance(error, discord.Forbidden):
            await ctx.send("❌ I don't have permission to access that channel.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid arguments. Usage: `$summarize <message_link> [count]`")
        else:
            # Let the base class handle other errors
            await super().cog_command_error(ctx, error)


async def setup(bot):
    """Required setup function for loading the cog"""
    await bot.add_cog(SummaryCog(bot))
