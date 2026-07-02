"""
Conversation Summary Cog — AI-powered conversation summaries using Google Gemini.
"""
from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import COLORS, BaseCog
from cogs.utils.gemini import GeminiError

from .cache import SummaryCache
from .message_parser import parse_message_link
from .prompts import (
    FOCUSED_SUMMARY_PROMPT,
    SUGGEST_TOPICS_PROMPT,
    SUMMARY_PROMPT,
    FocusedSummaryInput,
)

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

MAX_MESSAGES = 500


class SummaryCog(BaseCog):
    """AI-powered conversation summaries."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        self.cache = SummaryCache(ttl_seconds=3600)
        logger.info("SummaryCog initialized successfully")

    @commands.command(name='summarize', aliases=['summary', 'sum'])
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def summarize(self, ctx, start_link: str, end_link: str, *, topic: str | None = None):
        """
        Summarize a conversation between two message links.

        Usage:
            $sum <start_link> <end_link>
            $sum <start_link> <end_link> <topic>

        When a topic is provided, the summary focuses only on messages
        related to that topic and includes evidence links.

        Right-click a message > Copy Message Link to get links.
        """
        # Parse both links
        start_guild, start_channel, start_id = parse_message_link(start_link)
        end_guild, end_channel, end_id = parse_message_link(end_link)

        if start_guild is None or start_channel is None or start_id is None:
            await ctx.send("Invalid start message link.")
            return
        if end_guild is None or end_channel is None or end_id is None:
            await ctx.send("Invalid end message link.")
            return

        # Validate same channel
        if start_channel != end_channel:
            await ctx.send("Both links must be from the same channel.")
            return

        # Validate same guild
        if ctx.guild is None:
            return
        if ctx.guild.id != start_guild:
            await ctx.send("Those messages are from a different server.")
            return

        # Ensure start is before end (by message ID, which are chronological)
        if start_id > end_id:
            start_id, end_id = end_id, start_id

        channel = self.bot.get_channel(start_channel)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("I can't access that channel.")
            return

        # Check cache
        cache_key_suffix = f":{topic}" if topic else ""
        cached = self.cache.get(start_channel, start_id, end_id, suffix=cache_key_suffix)
        if cached:
            embed = self._build_embed(cached, 0, None, None, from_cache=True, topic=topic)
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
                        'link': f"https://discord.com/channels/{ctx.guild.id}/{start_channel}/{msg.id}",
                    })

            # Include start and end messages themselves if they're from users
            for boundary_msg in (start_msg, end_msg):
                if not boundary_msg.author.bot and boundary_msg.content.strip():
                    messages.append({
                        'author': boundary_msg.author.display_name,
                        'content': boundary_msg.content,
                        'timestamp': boundary_msg.created_at,
                        'link': f"https://discord.com/channels/{ctx.guild.id}/{start_channel}/{boundary_msg.id}",
                    })

            # Sort by timestamp (boundary messages were appended at the end)
            messages.sort(key=lambda m: m['timestamp'])

            if not messages:
                await processing.edit(content="No user messages found in that range.")
                return

            status = f"Summarizing {len(messages)} messages"
            if topic:
                status += f" (focused on: {topic})"
            status += "..."
            await processing.edit(content=status)

            gemini = self.bot.gemini
            if gemini is None:
                await processing.edit(content="Summaries are unavailable right now.")
                return
            try:
                if topic:
                    summary = await gemini.run(
                        FOCUSED_SUMMARY_PROMPT,
                        FocusedSummaryInput(messages=messages, topic=topic),
                    )
                else:
                    summary = await gemini.run(SUMMARY_PROMPT, messages)
            except GeminiError as e:
                logger.warning("Summary Gemini error code=%s: %s", e.code, e.message)
                await processing.edit(content=e.user_message)
                return

            self.cache.set(start_channel, start_id, end_id, summary, suffix=cache_key_suffix)

            start_time = messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M')
            end_time = messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M')
            embed = self._build_embed(summary, len(messages), start_time, end_time, topic=topic)
            await processing.edit(content=ctx.author.mention, embed=embed)

        except discord.Forbidden:
            await processing.edit(content="I don't have permission to access that channel.")
        except Exception as e:
            logger.error("Unexpected error in summarize: %s", e, exc_info=True)
            await processing.edit(content="An unexpected error occurred.")

    def _build_embed(self, summary: str, count: int,
                     start_time: str | None, end_time: str | None,
                     from_cache: bool = False,
                     topic: str | None = None) -> discord.Embed:
        title = "Conversation Summary"
        if topic:
            title = f"Evidence: {topic}"

        embed = discord.Embed(
            title=title,
            description=summary[:4000],
            color=random.choice(COLORS),
        )
        if not from_cache:
            embed.add_field(name="Messages", value=str(count), inline=True)
            embed.add_field(name="Range", value=f"{start_time} to {end_time}", inline=True)
        if topic:
            embed.add_field(name="Topic", value=topic, inline=False)

        footer = "AI-generated summary"
        if from_cache:
            footer += " (cached)"
        embed.set_footer(text=footer)
        return embed

    @commands.command(name='sumtopics', aliases=['sum_topics', 'sumfind'])
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def sumtopics(self, ctx, start_link: str, end_link: str):
        """
        Suggest focused topics to investigate in a message range.

        Usage:
            $sumtopics <start_link> <end_link>

        Returns actionable prompts you can pass to $sum as a topic.
        """
        start_guild, start_channel, start_id = parse_message_link(start_link)
        end_guild, end_channel, end_id = parse_message_link(end_link)

        if start_guild is None or start_channel is None or start_id is None:
            await ctx.send("Invalid start message link.")
            return
        if end_guild is None or end_channel is None or end_id is None:
            await ctx.send("Invalid end message link.")
            return

        if start_channel != end_channel:
            await ctx.send("Both links must be from the same channel.")
            return
        if ctx.guild is None:
            return
        if ctx.guild.id != start_guild:
            await ctx.send("Those messages are from a different server.")
            return

        if start_id > end_id:
            start_id, end_id = end_id, start_id

        channel = self.bot.get_channel(start_channel)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("I can't access that channel.")
            return

        processing = await ctx.send("Fetching messages...")

        try:
            try:
                start_msg = await channel.fetch_message(start_id)
                end_msg = await channel.fetch_message(end_id)
            except discord.NotFound:
                await processing.edit(content="One or both messages were not found.")
                return
            except discord.Forbidden:
                await processing.edit(content="I don't have permission to access that channel.")
                return

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

            for boundary_msg in (start_msg, end_msg):
                if not boundary_msg.author.bot and boundary_msg.content.strip():
                    messages.append({
                        'author': boundary_msg.author.display_name,
                        'content': boundary_msg.content,
                        'timestamp': boundary_msg.created_at,
                    })

            messages.sort(key=lambda m: m['timestamp'])

            if not messages:
                await processing.edit(content="No user messages found in that range.")
                return

            await processing.edit(content=f"Analyzing {len(messages)} messages for topics...")

            gemini = self.bot.gemini
            if gemini is None:
                await processing.edit(content="Topic suggestions are unavailable right now.")
                return
            try:
                result = await gemini.run(SUGGEST_TOPICS_PROMPT, messages)
            except GeminiError as e:
                logger.warning("Sumtopics Gemini error code=%s: %s", e.code, e.message)
                await processing.edit(content=e.user_message)
                return

            embed = discord.Embed(
                title="Suggested Topics",
                description=result[:4000],
                color=random.choice(COLORS),
            )
            embed.add_field(name="Messages analyzed", value=str(len(messages)), inline=True)
            embed.set_footer(text="Use these as topics with $sum <start> <end> <topic>")
            await processing.edit(content=ctx.author.mention, embed=embed)

        except discord.Forbidden:
            await processing.edit(content="I don't have permission to access that channel.")
        except Exception as e:
            logger.error("Unexpected error in sumtopics: %s", e, exc_info=True)
            await processing.edit(content="An unexpected error occurred.")

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
            await ctx.send("Usage: `$sum <start_link> <end_link> [topic]`")
        else:
            await super().cog_command_error(ctx, error)


async def setup(bot: Hablemos):
    if bot.gemini is None:
        logger.info("bot.gemini is None — SummaryCog will not load")
        return
    await bot.add_cog(SummaryCog(bot))
