"""Search cog — search messages in the server via Discord's Search API."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands
from discord.http import Route

from base_cog import BaseCog

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

# Discord returns ~25 results per page (fixed, not configurable)
RESULTS_PER_PAGE = 25
# How many results to show per page in the bot
DISPLAY_PER_PAGE = 5


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


def _message_link(guild_id: int, channel_id: str, message_id: str) -> str:
    """Build a Discord message jump link."""
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _format_result(msg: dict, index: int, guild_id: int) -> str:
    """Format a single search result for display."""
    author = msg.get("author", {})
    username = author.get("global_name") or author.get("username", "Unknown")
    content = msg.get("content", "")
    if len(content) > 120:
        content = content[:117] + "..."
    content = discord.utils.escape_markdown(content)

    channel_id = msg.get("channel_id", "")
    msg_id = msg.get("id", "")
    timestamp = msg.get("timestamp", "")[:10]
    link = _message_link(guild_id, channel_id, msg_id)

    return (
        f"**{index}.** {username} in <#{channel_id}> • {timestamp}\n"
        f"> {content or '*[no text content]*'}\n"
        f"-# [Jump to message]({link})"
    )


def _build_search_view(
    results: dict,
    guild_id: int,
    page: int,
    query_info: str,
) -> ui.LayoutView:
    """Build a Components V2 LayoutView for search results."""
    total = results.get("total_results", 0)
    messages = results.get("messages", [])

    view = ui.LayoutView(timeout=120)

    # Header
    view.add_item(ui.TextDisplay(f"## 🔍 Search Results\n-# {query_info}"))
    view.add_item(ui.Separator())

    # Results
    start_idx = page * DISPLAY_PER_PAGE
    page_msgs = messages[:DISPLAY_PER_PAGE]

    if not page_msgs:
        view.add_item(ui.TextDisplay("No results found."))
        return view

    lines: list[str] = []
    for i, msg_group in enumerate(page_msgs, start=start_idx + 1):
        if not msg_group:
            continue
        msg = msg_group[0]
        lines.append(_format_result(msg, i, guild_id))

    view.add_item(ui.TextDisplay("\n\n".join(lines)))

    # Footer with pagination info
    total_pages = max(1, (total + DISPLAY_PER_PAGE - 1) // DISPLAY_PER_PAGE)
    current_page = page + 1
    view.add_item(ui.Separator())
    view.add_item(ui.TextDisplay(
        f"-# Page {current_page}/{total_pages} • {total} total results"
    ))

    # Prev/Next buttons
    nav = ui.ActionRow()
    prev_btn = ui.Button(
        label="Previous",
        style=ButtonStyle.secondary,
        disabled=(page == 0),
        custom_id="search:prev",
    )
    next_btn = ui.Button(
        label="Next",
        style=ButtonStyle.secondary,
        disabled=(current_page >= total_pages),
        custom_id="search:next",
    )
    nav.add_item(prev_btn)
    nav.add_item(next_btn)
    view.add_item(nav)

    return view


class SearchState:
    """Tracks the search state for pagination."""

    __slots__ = ("author_id", "channel_id", "content", "guild_id", "has_filter", "page", "total")

    def __init__(
        self,
        guild_id: int,
        content: str | None,
        author_id: int | None,
        channel_id: int | None,
        has_filter: str | None,
    ):
        self.guild_id = guild_id
        self.content = content
        self.author_id = author_id
        self.channel_id = channel_id
        self.has_filter = has_filter
        self.page = 0
        self.total = 0

    @property
    def offset(self) -> int:
        return self.page * DISPLAY_PER_PAGE

    @property
    def query_info(self) -> str:
        parts = []
        if self.content:
            parts.append(f'"{self.content}"')
        if self.author_id:
            parts.append(f"author: <@{self.author_id}>")
        if self.channel_id:
            parts.append(f"channel: <#{self.channel_id}>")
        if self.has_filter:
            parts.append(f"has: {self.has_filter}")
        return " • ".join(parts) or "all messages"


class SearchCog(BaseCog):
    """Search messages in the server."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        # Map message_id -> SearchState for active pagination sessions
        self._sessions: dict[int, SearchState] = {}

    @commands.command(name="search")
    @commands.has_permissions(manage_messages=True)
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

        state = SearchState(ctx.guild.id, content, author_id, channel_id, has_filter)

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
                    offset=0,
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

        state.total = results.get("total_results", 0)
        if not results.get("messages"):
            await ctx.send("🔍 No results found.")
            return

        view = _build_search_view(results, ctx.guild.id, 0, state.query_info)
        msg = await ctx.send(view=view)
        self._sessions[msg.id] = state

    @app_commands.command(name="search", description="Search for messages in this server")
    @app_commands.default_permissions(manage_messages=True)
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
            await interaction.followup.send(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        author_id = author.id if author else None
        channel_id = channel.id if channel else None
        state = SearchState(guild_id, query, author_id, channel_id, has)

        try:
            results = await _search_guild(
                self.bot,
                guild_id,
                content=query,
                author_id=author_id,
                channel_id=channel_id,
                has=has,
                sort_by="relevance",
                offset=0,
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

        state.total = results.get("total_results", 0)
        if not results.get("messages"):
            await interaction.followup.send("🔍 No results found.")
            return

        view = _build_search_view(results, guild_id, 0, state.query_info)
        msg = await interaction.followup.send(view=view, wait=True)
        self._sessions[msg.id] = state

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        """Handle prev/next button clicks for search pagination."""
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id not in ("search:prev", "search:next"):
            return

        message_id = interaction.message.id if interaction.message else None
        if message_id is None:
            return

        state = self._sessions.get(message_id)
        if state is None:
            await interaction.response.send_message(
                "This search session has expired. Run a new search.", ephemeral=True
            )
            return

        # Update page
        if custom_id == "search:next":
            state.page += 1
        else:
            state.page = max(0, state.page - 1)

        await interaction.response.defer()

        try:
            results = await _search_guild(
                self.bot,
                state.guild_id,
                content=state.content,
                author_id=state.author_id,
                channel_id=state.channel_id,
                has=state.has_filter,
                sort_by="relevance",
                offset=state.offset,
            )
        except discord.HTTPException as e:
            logger.error("Search pagination error: %s", e)
            await interaction.followup.send(
                "An error occurred. Please try again.", ephemeral=True
            )
            return

        state.total = results.get("total_results", 0)
        view = _build_search_view(results, state.guild_id, state.page, state.query_info)
        if interaction.message:
            await interaction.message.edit(view=view)


async def setup(bot: Hablemos):
    await bot.add_cog(SearchCog(bot))
