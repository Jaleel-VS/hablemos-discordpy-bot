"""Search cog — search messages in the server via Discord's Search API."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Color, Embed, Interaction, app_commands
from discord.ext import commands
from discord.http import Route

from base_cog import BaseCog

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

# Discord returns ~25 results per page (fixed, not configurable)
RESULTS_PER_PAGE = 25


async def _search_guild(
    bot: Hablemos,
    guild_id: int,
    *,
    content: str | None = None,
    author_id: int | None = None,
    channel_id: int | None = None,
    mentions: int | None = None,
    has: str | None = None,
    min_id: int | None = None,
    max_id: int | None = None,
    sort_by: str = "relevance",
    sort_order: str = "desc",
    offset: int = 0,
    include_nsfw: bool = False,
) -> dict:
    """Call the Search Guild Messages endpoint.

    Returns a dict with keys: total_results, messages, analytics_id.
    Raises discord.HTTPException on failure.
    """
    params: dict[str, str | int | bool] = {}
    if content is not None:
        params["content"] = content
    if author_id is not None:
        params["author_id"] = author_id
    if channel_id is not None:
        params["channel_id"] = channel_id
    if mentions is not None:
        params["mentions"] = mentions
    if has is not None:
        params["has"] = has
    if min_id is not None:
        params["min_id"] = min_id
    if max_id is not None:
        params["max_id"] = max_id
    if sort_by:
        params["sort_by"] = sort_by
    if sort_order:
        params["sort_order"] = sort_order
    if offset:
        params["offset"] = offset
    if include_nsfw:
        params["include_nsfw"] = "true"

    route = Route(
        "GET",
        "/guilds/{guild_id}/messages/search",
        guild_id=guild_id,
    )
    return await bot.http.request(route, params=params)


def _format_result(msg: dict, index: int) -> str:
    """Format a single search result for display."""
    author = msg.get("author", {})
    username = author.get("global_name") or author.get("username", "Unknown")
    content = msg.get("content", "")
    # Truncate long content
    if len(content) > 150:
        content = content[:147] + "..."
    # Escape any markdown to avoid formatting issues
    content = discord.utils.escape_markdown(content)

    channel_id = msg.get("channel_id", "")
    timestamp = msg.get("timestamp", "")[:10]  # Just the date part

    return (
        f"**{index}.** {username} in <#{channel_id}> ({timestamp})\n"
        f"> {content or '*[no text content]*'}"
    )


class SearchCog(BaseCog):
    """Search messages in the server."""

    @commands.command(name="search")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def search_prefix(self, ctx: commands.Context, *, query: str):
        """Search for messages in this server.

        Usage: $search <query>
        Filters: author:@user channel:#channel has:link/embed/file
        """
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        # Parse inline filters from the query
        author_id = None
        channel_id = None
        has_filter = None

        parts = query.split()
        clean_parts = []
        for part in parts:
            if part.startswith("author:"):
                # Support raw ID or mention
                raw = part[7:].strip("<@!>")
                if raw.isdigit():
                    author_id = int(raw)
            elif part.startswith("channel:"):
                raw = part[8:].strip("<#>")
                if raw.isdigit():
                    channel_id = int(raw)
            elif part.startswith("has:"):
                val = part[4:]
                if val in ("link", "embed", "file"):
                    has_filter = val
            else:
                clean_parts.append(part)

        content = " ".join(clean_parts) or None

        if not content and not author_id and not channel_id and not has_filter:
            await ctx.send("Please provide a search query or filter.")
            return

        async with ctx.typing():
            try:
                results = await _search_guild(
                    self.bot,
                    ctx.guild.id,
                    content=content,
                    author_id=author_id,
                    channel_id=channel_id,
                    has=has_filter,
                    sort_by="relevance",
                )
            except discord.HTTPException as e:
                if e.code == 110000:
                    await ctx.send(
                        "🔍 Search index not ready for this server. Try again in a moment."
                    )
                    return
                logger.error("Search API error: %s", e)
                await ctx.send("An error occurred while searching. Please try again later.")
                return

        total = results.get("total_results", 0)
        messages = results.get("messages", [])

        if not messages:
            await ctx.send("🔍 No results found.")
            return

        # Format top 5 results
        lines = []
        for i, msg_group in enumerate(messages[:5], start=1):
            if not msg_group:
                continue
            msg = msg_group[0]
            lines.append(_format_result(msg, i))

        description = "\n\n".join(lines)
        embed = Embed(
            title=f"🔍 Search Results ({total} total)",
            description=description,
            color=Color(0x00FF00),
        )
        if total > 5:
            embed.set_footer(text=f"Showing top 5 of {total} results")

        await ctx.send(embed=embed)

    @app_commands.command(name="search", description="Search for messages in this server")
    @app_commands.describe(
        query="What to search for",
        author="Filter by message author",
        channel="Filter by channel",
        has="Filter by attachment type",
    )
    @app_commands.choices(
        has=[
            app_commands.Choice(name="Link", value="link"),
            app_commands.Choice(name="Embed", value="embed"),
            app_commands.Choice(name="File", value="file"),
        ]
    )
    @app_commands.guild_only()
    async def search_slash(
        self,
        interaction: Interaction,
        query: str | None = None,
        author: discord.Member | None = None,
        channel: discord.TextChannel | None = None,
        has: str | None = None,
    ):
        """Search for messages in this server."""
        if not query and not author and not channel and not has:
            await interaction.response.send_message(
                "Please provide at least one search filter.", ephemeral=True
            )
            return

        await interaction.response.defer()

        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            results = await _search_guild(
                self.bot,
                guild_id,
                content=query,
                author_id=author.id if author else None,
                channel_id=channel.id if channel else None,
                has=has,
                sort_by="relevance",
            )
        except discord.HTTPException as e:
            if e.code == 110000:
                await interaction.followup.send(
                    "🔍 Search index not ready for this server. Try again in a moment.",
                    ephemeral=True,
                )
                return
            logger.error("Search API error: %s", e)
            await interaction.followup.send(
                "An error occurred while searching. Please try again later.",
                ephemeral=True,
            )
            return

        total = results.get("total_results", 0)
        messages = results.get("messages", [])

        if not messages:
            await interaction.followup.send("🔍 No results found.")
            return

        lines = []
        for i, msg_group in enumerate(messages[:5], start=1):
            if not msg_group:
                continue
            msg = msg_group[0]
            lines.append(_format_result(msg, i))

        description = "\n\n".join(lines)
        embed = Embed(
            title=f"🔍 Search Results ({total} total)",
            description=description,
            color=Color(0x00FF00),
        )
        if total > 5:
            embed.set_footer(text=f"Showing top 5 of {total} results")

        await interaction.followup.send(embed=embed)


async def setup(bot: Hablemos):
    await bot.add_cog(SearchCog(bot))
