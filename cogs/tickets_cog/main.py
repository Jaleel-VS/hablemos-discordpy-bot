"""
Tickets cog — quick overview of open moderation tickets across forum channels.
"""
import logging

import discord
from discord import Color, ui
from discord.ext import commands

from base_cog import BaseCog

from .config import ADMIN_FORUM_ID, FILTERED_THREADS, OPEN_TAGS, STAFF_FORUM_ID

logger = logging.getLogger(__name__)


def _is_open(thread: discord.Thread, open_tag_names: set[str]) -> bool:
    """Check if a thread has any tag matching the open tags list."""
    if thread.name.lower() in FILTERED_THREADS:
        return False
    return any(tag.name.lower() in open_tag_names for tag in thread.applied_tags)


async def _format_thread(thread: discord.Thread, open_tag_names: set[str]) -> str:
    """Format a single thread as a line item with last interaction info."""
    responded = "✅" if thread.message_count > 1 else "⏳"
    tags = " ".join(f"`{tag.name}`" for tag in thread.applied_tags if tag.name.lower() not in open_tag_names)
    line = f"{responded} [{thread.name}]({thread.jump_url}) {tags}".rstrip()

    try:
        msgs = [msg async for msg in thread.history(limit=1)]
        if msgs:
            msg = msgs[0]
            timestamp = discord.utils.format_dt(msg.created_at, "R")
            line += f"\n-# Last interaction: {timestamp} by {msg.author.mention}"
    except (discord.Forbidden, discord.HTTPException):
        pass

    return line


def _loading_view() -> ui.LayoutView:
    """Build a loading placeholder view."""
    view = ui.LayoutView()
    view.add_item(ui.Container(
        ui.TextDisplay("## Open Tickets\n⏳ Fetching tickets..."),
        accent_colour=Color.orange(),
    ))
    return view


def _tickets_view(sections: list[tuple[str, str]], total: int) -> ui.LayoutView:
    """Build the final tickets layout view."""
    children: list[ui.Item] = [
        ui.TextDisplay("## Open Tickets"),
        ui.Separator(visible=True),
    ]

    for name, value in sections:
        children.append(ui.TextDisplay(f"**{name}**\n{value}"))

    children.append(ui.Separator(visible=True))
    children.append(ui.TextDisplay(
        f"-# {total} open · ✅ = responded · ⏳ = awaiting response"
    ))

    view = ui.LayoutView()
    view.add_item(ui.Container(*children, accent_colour=Color.orange()))
    return view


class TicketsCog(BaseCog):
    """Mod-only ticket overview for forum channels."""

    @commands.command(name='tickets')
    @commands.has_permissions(manage_messages=True)
    async def tickets(self, ctx: commands.Context):
        """
        Show open tickets across mod forum channels.

        Usage: $tickets
        """
        open_tags = {t.strip().lower() for t in OPEN_TAGS}
        forums = []

        for fid in (STAFF_FORUM_ID, ADMIN_FORUM_ID):
            if fid == 0:
                continue
            channel = self.bot.get_channel(fid)
            if isinstance(channel, discord.ForumChannel):
                forums.append(channel)

        if not forums:
            await ctx.send("No forum channels configured. Set `STAFF_FORUM_ID` / `ADMIN_FORUM_ID`.")
            return

        # Send loading state
        msg = await ctx.send(view=_loading_view())

        sections: list[tuple[str, str]] = []
        total = 0

        for forum in forums:
            open_threads = [t for t in forum.threads if _is_open(t, open_tags)]
            open_threads.sort(key=lambda t: t.created_at or t.id)

            if open_threads:
                lines = [await _format_thread(t, open_tags) for t in open_threads]
                value = "\n".join(lines)
                if len(value) > 900:
                    value = value[:896] + "\n..."
            else:
                value = "No open tickets 🎉"

            sections.append((f"#{forum.name} ({len(open_threads)})", value))
            total += len(open_threads)

        # Edit with final view
        try:
            await msg.edit(view=_tickets_view(sections, total))
        except discord.HTTPException:
            logger.exception("Failed to edit tickets message")


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
