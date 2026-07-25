"""
Tickets cog — quick overview of open moderation tickets across forum channels.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import Color, ui
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.checks import min_role

from .config import (
    ADMIN_FORUM_ID,
    FILTERED_THREADS,
    NOTIFY_CHANNEL_ID,
    OPEN_TAGS,
    STAFF_FORUM_ID,
    TICKETSUB_MIN_ROLE_ID,
)
from .views import TicketSubView

if TYPE_CHECKING:
    from hablemos import Hablemos

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


# Open tickets shown per page in the paginated overview. Each entry is a
# two-line block (title + last-interaction), so 8 stays well within
# Discord's Components V2 size budget.
PAGE_SIZE = 8


def _loading_view() -> ui.LayoutView:
    """Build a loading placeholder view."""
    view = ui.LayoutView()
    view.add_item(ui.Container(
        ui.TextDisplay("## Open Tickets\n⏳ Fetching tickets..."),
        accent_colour=Color.orange(),
    ))
    return view


def _empty_tickets_view() -> ui.LayoutView:
    """View shown when no forum has any open tickets."""
    view = ui.LayoutView()
    view.add_item(ui.Container(
        ui.TextDisplay("## Open Tickets\nNo open tickets 🎉"),
        accent_colour=Color.green(),
    ))
    return view


class TicketsView(ui.LayoutView):
    """Paginated ◀/▶ overview of open tickets (flat list, N per page).

    Entries are a flat list of (forum_name, formatted_line) across every
    watched forum. Only the invoking mod can flip pages; buttons disable
    on timeout so the last page stays readable.
    """

    def __init__(
        self,
        invoker_id: int,
        entries: list[tuple[str, str]],
        total: int,
        *,
        page: int = 0,
        timeout: float = 300,
    ) -> None:
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.entries = entries
        self.total = total
        self.page = page
        self._rebuild()

    @property
    def page_count(self) -> int:
        return max(1, (len(self.entries) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _rebuild(self) -> None:
        self.clear_items()

        start = self.page * PAGE_SIZE
        page_entries = self.entries[start:start + PAGE_SIZE]

        children: list[ui.Item] = [
            ui.TextDisplay("## Open Tickets"),
            ui.Separator(visible=True),
        ]

        # Group this page's entries under their forum name, only emitting a
        # header when the forum changes so a forum spanning a page boundary
        # still reads cleanly.
        current_forum: str | None = None
        for forum_name, line in page_entries:
            if forum_name != current_forum:
                children.append(ui.TextDisplay(f"**{forum_name}**"))
                current_forum = forum_name
            children.append(ui.TextDisplay(line))

        children.append(ui.Separator(visible=True))
        children.append(ui.TextDisplay(
            f"-# {self.total} open · page {self.page + 1}/{self.page_count} · "
            "✅ = responded · ⏳ = awaiting response"
        ))

        prev_btn = ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            disabled=self.page <= 0,
        )
        prev_btn.callback = self._prev
        next_btn = ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= self.page_count - 1,
        )
        next_btn.callback = self._next
        children.append(ui.ActionRow(prev_btn, next_btn))

        self.add_item(ui.Container(*children, accent_colour=Color.orange()))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the person who ran this command can flip pages.",
                ephemeral=True,
            )
            return False
        return True

    async def _prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _next(self, interaction: discord.Interaction) -> None:
        self.page = min(self.page_count - 1, self.page + 1)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        """Disable the nav buttons when the view expires."""
        for item in self.walk_children():
            if isinstance(item, ui.Button):
                item.disabled = True


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

        # Flat list of (forum_name, formatted_line) across every forum, in
        # forum order then thread-creation order. Pagination is by entry
        # count, so long forums no longer get silently truncated.
        entries: list[tuple[str, str]] = []
        total = 0

        for forum in forums:
            open_threads = [t for t in forum.threads if _is_open(t, open_tags)]
            open_threads.sort(key=lambda t: t.created_at or t.id)
            forum_label = f"#{forum.name} ({len(open_threads)})"
            for thread in open_threads:
                line = await _format_thread(thread, open_tags)
                entries.append((forum_label, line))
            total += len(open_threads)

        if total == 0:
            try:
                await msg.edit(view=_empty_tickets_view())
            except discord.HTTPException:
                logger.exception("Failed to edit tickets message")
            return

        # Edit with final paginated view
        try:
            await msg.edit(view=TicketsView(ctx.author.id, entries, total))
        except discord.HTTPException:
            logger.exception("Failed to edit tickets message")

    @commands.command(name='ticketsub')
    @min_role(TICKETSUB_MIN_ROLE_ID)
    async def ticketsub(self, ctx: commands.Context):
        """
        Manage your per-forum ticket notification subscriptions.

        Opens a menu to choose which mod forums you want to be
        pinged for when new tickets are opened.

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

        # Migrate legacy "all forums" subscriptions on first use
        forum_ids = list(_watched_forum_ids())
        await self.bot.db.migrate_legacy_ticket_subs(guild_id, forum_ids)

        # Build list of (forum_id, display_name) for available forums
        forums: list[tuple[int, str]] = []
        for fid in forum_ids:
            channel = self.bot.get_channel(fid)
            if isinstance(channel, discord.ForumChannel):
                forums.append((fid, channel.name))
            else:
                forums.append((fid, f"Forum {fid}"))

        if not forums:
            await ctx.send("No forum channels configured.")
            return

        subscribed = await self.bot.db.get_ticket_subscribed_forums(user_id, guild_id)
        subscribed_ids = {fid for fid in subscribed if fid != 0}

        # Build status embed
        if subscribed_ids:
            names = [n for fid, n in forums if fid in subscribed_ids]
            listing = ", ".join(f"**#{n}**" for n in names)
            description = f"🔔 Currently subscribed to: {listing}"
            color = discord.Color.green()
        else:
            description = "🔕 You're not subscribed to any ticket forums."
            color = discord.Color.orange()

        embed = discord.Embed(description=description, color=color)
        embed.set_footer(text="Select the forums you want notifications for.")

        view = TicketSubView(
            user_id=user_id,
            forums=forums,
            subscribed_ids=subscribed_ids,
        )
        await ctx.send(embed=embed, view=view)

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

        forum_id = thread.parent_id
        if forum_id is None:
            return

        subscribers = await self.bot.db.get_ticket_subscribers(guild.id, forum_id)
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


async def setup(bot: Hablemos):
    await bot.add_cog(TicketsCog(bot))
