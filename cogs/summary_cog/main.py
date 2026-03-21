"""
Conversation Summary Cog — AI-powered conversation summaries using Google Gemini.
"""
import logging
import random

import discord
from discord.ext import commands

from base_cog import BaseCog, COLORS
from .gemini_client import GeminiClient
from .cache import SummaryCache
from .message_parser import parse_message_link

logger = logging.getLogger(__name__)

MAX_MESSAGES = 500


class SummaryCog(BaseCog):
    """Cog for AI-powered conversation summaries using Gemini."""

    def __init__(self, bot):
        super().__init__(bot)
        self.gemini = GeminiClient()
        self.cache = SummaryCache(ttl_seconds=3600)
        logger.info("SummaryCog initialized successfully")

    @commands.command(name='summarize', aliases=['summary', 'sum'])
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def summarize(self, ctx, start_link: str, end_link: str):
        """
        Summarize a conversation between two message links.

        Usage:
            $summarize <start_link> <end_link>
            $sum <start_link> <end_link>

        Right-click a message > Copy Message Link to get links.
        """
        # Parse both links
        start_guild, start_channel, start_id = parse_message_link(start_link)
        end_guild, end_channel, end_id = parse_message_link(end_link)

        if not all([start_guild, start_channel, start_id]):
            await ctx.send("Invalid start message link.")
            return
        if not all([end_guild, end_channel, end_id]):
            await ctx.send("Invalid end message link.")
            return

        # Validate same channel
        if start_channel != end_channel:
            await ctx.send("Both links must be from the same channel.")
            return

        # Validate same guild
        if ctx.guild.id != start_guild:
            await ctx.send("Those messages are from a different server.")
            return

        # Ensure start is before end (by message ID, which are chronological)
        if start_id > end_id:
            start_id, end_id = end_id, start_id

        channel = self.bot.get_channel(start_channel)
        if not channel:
            await ctx.send("I can't access that channel.")
            return

        # Check cache
        cached = self.cache.get(start_channel, start_id, end_id)
        if cached:
            embed = self._build_embed(cached, 0, None, None, from_cache=True)
            await ctx.send(ctx.author.mention, embed=embed)
            return

        processing = await ctx.send("Fetching messages...")

        try:
            # Fetch start and end messages to validate they exist
            try:
                start_msg = await channel.fetch_message(start_id)
                end_msg = await channel.fetch_message(end_id)
            except discord.NotFound:
                await processing.edit(content="One or both messages were not found. They may have been deleted.")
                return
            except discord.Forbidden:
                await processing.edit(content="I don't have permission to access that channel.")
                return

            # Fetch messages in the range (inclusive of start, up to end)
            messages = []
            async for msg in channel.history(
                limit=MAX_MESSAGES,
                after=start_msg,
                before=end_msg,
                oldest_first=True,
            ):
                if not msg.author.bot and msg.content.strip():
                    messages.append({
                        'author': msg.author.display_name,
                        'content': msg.content,
                        'timestamp': msg.created_at,
                    })

            # Include start and end messages themselves if they're from users
            for boundary_msg in (start_msg, end_msg):
                if not boundary_msg.author.bot and boundary_msg.content.strip():
                    messages.append({
                        'author': boundary_msg.author.display_name,
                        'content': boundary_msg.content,
                        'timestamp': boundary_msg.created_at,
                    })

            # Sort by timestamp (boundary messages were appended at the end)
            messages.sort(key=lambda m: m['timestamp'])

            if not messages:
                await processing.edit(content="No user messages found in that range.")
                return

            await processing.edit(content=f"Summarizing {len(messages)} messages...")

            try:
                summary = self.gemini.generate_summary(messages)
            except Exception as e:
                logger.error(f"Gemini API error: {e}", exc_info=True)
                error_str = str(e).lower()
                if any(k in error_str for k in ('rate', 'quota', '429')):
                    await processing.edit(content="API rate limit reached. Try again in a few minutes.")
                elif 'safety' in error_str or 'blocked' in error_str:
                    await processing.edit(content="Summary blocked by content policy.")
                else:
                    await processing.edit(content="Failed to generate summary. Try again later.")
                return

            self.cache.set(start_channel, start_id, end_id, summary)

            start_time = messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M')
            end_time = messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M')
            embed = self._build_embed(summary, len(messages), start_time, end_time)
            await processing.edit(content=ctx.author.mention, embed=embed)

        except discord.Forbidden:
            await processing.edit(content="I don't have permission to access that channel.")
        except Exception as e:
            logger.error(f"Unexpected error in summarize: {e}", exc_info=True)
            await processing.edit(content="An unexpected error occurred.")

    def _build_embed(self, summary: str, count: int,
                     start_time: str | None, end_time: str | None,
                     from_cache: bool = False) -> discord.Embed:
        embed = discord.Embed(
            title="Conversation Summary",
            description=summary[:4000],
            color=random.choice(COLORS),
        )
        if not from_cache:
            embed.add_field(name="Messages", value=str(count), inline=True)
            embed.add_field(name="Range", value=f"{start_time} to {end_time}", inline=True)

        footer = "AI-generated summary"
        if from_cache:
            footer += " (cached)"
        embed.set_footer(text=footer)
        return embed

    @commands.command(name='summary_stats', aliases=['sum_stats'])
    @commands.is_owner()
    async def summary_stats(self, ctx):
        """Show summary cache statistics."""
        stats = self.cache.get_stats()
        embed = discord.Embed(title="Summary Cache Stats", color=0x3498db)
        embed.add_field(
            name="Usage",
            value=(
                f"**Size:** {stats['size']}\n"
                f"**Requests:** {stats['total_requests']}\n"
                f"**Hit rate:** {stats['hit_rate']:.1f}%"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name='clear_summary_cache', aliases=['sum_clear'])
    @commands.is_owner()
    async def clear_cache(self, ctx):
        """Clear the summary cache."""
        count = self.cache.clear()
        await ctx.send(f"Cache cleared. Removed {count} entries.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need Manage Messages permission to use this.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Cooldown. Try again in {error.retry_after:.0f}s.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `$summarize <start_link> <end_link>`")
        else:
            await super().cog_command_error(ctx, error)


async def setup(bot):
    await bot.add_cog(SummaryCog(bot))
