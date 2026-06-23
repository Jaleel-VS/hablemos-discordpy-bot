"""
Tickets cog — quick overview of open moderation tickets across forum channels.
"""
import logging

import discord
from discord import Color, ui
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, yellow_embed

from .config import (
    ADMIN_FORUM_ID,
    FILTERED_THREADS,
    NOTIFY_CHANNEL_ID,
    OPEN_TAGS,
    STAFF_FORUM_ID,
)

logger = logging.getLogger(__name__)


def _is_open(thread: discord.Thread, open_tag_names: set[str]) -> bool:
    """Check if a thread has any tag matching the open tags list."""
    if thread.name.lower() in FILTERED_THREADS:
        return False
    return any(tag.name.lower() in open_tag_names for tag in thread.applied_tags)


def _watched_forum_ids() -> set[int]:
    """Configured ticket forum IDs, excluding unset (0) entries."""
    return {fid for fid in (STAFF_FORUM_ID, ADMIN_FORUM_ID) if fid != 0}


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

        for fid in _watched_forum_ids():
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
                # Truncate at last complete ticket entry to avoid cutting off mid-entry
                MAX_LENGTH = 900
                truncated_lines = []
                char_count = 0
                omitted = 0

                for entry in lines:
                    # Check if adding this entry would exceed limit
                    # +1 for the newline that will join entries
                    entry_length = len(entry) + (1 if truncated_lines else 0)
                    if char_count + entry_length <= MAX_LENGTH:
                        truncated_lines.append(entry)
                        char_count += entry_length
                    else:
                        omitted += 1

                value = "\n".join(truncated_lines)
                if omitted > 0:
                    suffix = f"\n-# ...and {omitted} more"
                    # Ensure suffix fits
                    if len(value) + len(suffix) > MAX_LENGTH:
                        # Remove last entry to make room
                        truncated_lines.pop()
                        omitted += 1
                        value = "\n".join(truncated_lines) + suffix
                    else:
                        value += suffix
            else:
                value = "No open tickets 🎉"

            sections.append((f"#{forum.name} ({len(open_threads)})", value))
            total += len(open_threads)

        # Edit with final view
        try:
            await msg.edit(view=_tickets_view(sections, total))
        except discord.HTTPException:
            logger.exception("Failed to edit tickets message")

    @commands.command(name='ticketsub')
    @commands.has_permissions(manage_messages=True)
    async def ticketsub(self, ctx: commands.Context):
        """
        Toggle your subscription to new-ticket pings.

        When subscribed, you'll be mentioned in the configured notification
        channel whenever a new open ticket is opened in a mod forum.

        Usage: $ticketsub
        """
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        if NOTIFY_CHANNEL_ID == 0:
            await ctx.send(
                "Ticket notifications aren't configured. "
                "Ask an admin to set `TICKETS_NOTIFY_CHANNEL_ID`."
            )
            return

        user_id = ctx.author.id
        guild_id = ctx.guild.id

        if await self.bot.db.is_ticket_subscribed(user_id, guild_id):
            await self.bot.db.remove_ticket_subscription(user_id, guild_id)
            await ctx.send(embed=yellow_embed(
                "🔕 You'll no longer be pinged when new tickets arrive."
            ))
        else:
            await self.bot.db.add_ticket_subscription(user_id, guild_id)
            await ctx.send(embed=green_embed(
                f"🔔 You'll be pinged in <#{NOTIFY_CHANNEL_ID}> when new tickets arrive."
            ))

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Ping subscribers when a new ticket is opened in a mod forum."""
        if NOTIFY_CHANNEL_ID == 0:
            return
        if thread.parent_id not in _watched_forum_ids():
            return
        # A freshly created thread may not have its tags applied yet, so we
        # don't gate on the Open tag here — every new ticket is, by
        # definition, unhandled. We only skip the explicitly filtered ones.
        if thread.name.lower() in FILTERED_THREADS:
            return

        guild = thread.guild
        if guild is None:
            return

        subscribers = await self.bot.db.get_ticket_subscribers(guild.id)
        if not subscribers:
            return

        channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Tickets notify channel %s is missing or not messageable",
                NOTIFY_CHANNEL_ID,
            )
            return

        mentions = " ".join(f"<@{uid}>" for uid in subscribers)
        forum_name = thread.parent.name if thread.parent else "tickets"
        content = (
            f"🎫 New ticket in **#{forum_name}**: "
            f"[{thread.name}]({thread.jump_url})\n{mentions}"
        )
        try:
            await channel.send(
                content,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Failed to send new-ticket notification")


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
