"""
Tickets cog — quick overview of open moderation tickets across forum channels.
"""
import logging

import discord
from discord.ext import commands

from base_cog import BaseCog
from .config import STAFF_FORUM_ID, ADMIN_FORUM_ID, OPEN_TAGS

logger = logging.getLogger(__name__)


def _is_open(thread: discord.Thread, open_tag_names: set[str]) -> bool:
    """Check if a thread has any tag matching the open tags list."""
    return any(tag.name.lower() in open_tag_names for tag in thread.applied_tags)


def _format_thread(thread: discord.Thread) -> str:
    """Format a single thread as a line item."""
    responded = "✅" if thread.message_count > 1 else "⏳"
    owner_mention = f"<@{thread.owner_id}>"
    return f"{responded} [{thread.name}]({thread.jump_url}) — {owner_mention}"


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

        embed = discord.Embed(title="Open Tickets", color=discord.Color.orange())
        total = 0

        for forum in forums:
            open_threads = [t for t in forum.threads if _is_open(t, open_tags)]
            open_threads.sort(key=lambda t: t.created_at or t.id)

            if open_threads:
                lines = [_format_thread(t) for t in open_threads]
                value = '\n'.join(lines)
                # Embed field value limit is 1024
                if len(value) > 1024:
                    value = value[:1020] + "\n..."
            else:
                value = "No open tickets 🎉"

            embed.add_field(name=f"#{forum.name} ({len(open_threads)})", value=value, inline=False)
            total += len(open_threads)

        embed.set_footer(text=f"{total} open · ✅ = responded · ⏳ = awaiting response")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
