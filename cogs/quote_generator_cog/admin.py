"""
Quote Generator Admin Cog

Admin-only commands for managing quote usage:
ban/unban users, pause/unpause quotes, block/unblock channels.
All commands require bot owner permissions.
"""
import discord
from discord.ext import commands
from discord import Embed
from base_cog import BaseCog
import logging
import re
import time

logger = logging.getLogger(__name__)

DURATION_PATTERN = re.compile(r'^(\d+)([mhd])$')

def parse_duration(text: str) -> int | None:
    """Parse a duration string like 30m, 2h, 1d into seconds. Returns None if invalid."""
    match = DURATION_PATTERN.match(text.strip().lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    multipliers = {'m': 60, 'h': 3600, 'd': 86400}
    return value * multipliers[unit]


class QuoteAdminCog(BaseCog):
    """Admin-only commands for quote management"""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @commands.command(name="quoteadmin")
    @commands.is_owner()
    async def quoteadmin(self, ctx, action: str = None, *, target: str = None):
        """
        Admin quote management (Owner only)

        Available actions:
        - ban <@user|user_id>: Ban user from making quotes
        - unban <@user|user_id>: Unban user
        - pause <duration>: Pause quotes (e.g. 30m, 2h, 1d)
        - unpause: Unpause immediately
        - blockchannel <#channel>: Block quotes in a channel
        - unblockchannel <#channel>: Unblock channel
        - status: Show banned users, banned channels, pause state
        """
        if not action:
            await ctx.send(
                "Usage: `$quoteadmin <ban|unban|pause|unpause|blockchannel|unblockchannel|status> [target]`"
            )
            return

        action = action.lower()

        if action == "ban":
            await self._handle_ban(ctx, target)
        elif action == "unban":
            await self._handle_unban(ctx, target)
        elif action == "pause":
            await self._handle_pause(ctx, target)
        elif action == "unpause":
            await self._handle_unpause(ctx)
        elif action == "blockchannel":
            await self._handle_blockchannel(ctx)
        elif action == "unblockchannel":
            await self._handle_unblockchannel(ctx)
        elif action == "status":
            await self._handle_status(ctx)
        else:
            await ctx.send(f"Unknown action: `{action}`")

    async def _handle_ban(self, ctx, target):
        """Ban a user from using quote commands"""
        if not target:
            await ctx.send("Usage: `$quoteadmin ban <@user|user_id>`")
            return

        try:
            if ctx.message.mentions:
                user_id = ctx.message.mentions[0].id
            else:
                user_id = int(target.strip())

            await self.bot.db.quote_ban_user(user_id, ctx.author.id)
            await ctx.send(f"Banned user `{user_id}` from quote commands.")
            logger.info(f"Admin {ctx.author} quote-banned user {user_id}")
        except ValueError:
            await ctx.send("Invalid user ID.")

    async def _handle_unban(self, ctx, target):
        """Unban a user from quote commands"""
        if not target:
            await ctx.send("Usage: `$quoteadmin unban <@user|user_id>`")
            return

        try:
            if ctx.message.mentions:
                user_id = ctx.message.mentions[0].id
            else:
                user_id = int(target.strip())

            success = await self.bot.db.quote_unban_user(user_id)
            if success:
                await ctx.send(f"Unbanned user `{user_id}` from quote commands.")
                logger.info(f"Admin {ctx.author} quote-unbanned user {user_id}")
            else:
                await ctx.send(f"User `{user_id}` was not banned.")
        except ValueError:
            await ctx.send("Invalid user ID.")

    async def _handle_pause(self, ctx, target):
        """Pause all quote usage for a duration"""
        if not target:
            await ctx.send("Usage: `$quoteadmin pause <duration>` (e.g. `30m`, `2h`, `1d`)")
            return

        seconds = parse_duration(target)
        if seconds is None:
            await ctx.send("Invalid duration. Use format like `30m`, `2h`, or `1d`.")
            return

        paused_until = int(time.time()) + seconds
        await self.bot.db.set_bot_setting('quote_paused_until', paused_until)
        await ctx.send(f"Quotes paused until <t:{paused_until}:F> (<t:{paused_until}:R>).")
        logger.info(f"Admin {ctx.author} paused quotes until {paused_until}")

    async def _handle_unpause(self, ctx):
        """Unpause quotes immediately"""
        await self.bot.db.set_bot_setting('quote_paused_until', 0)
        await ctx.send("Quotes have been unpaused.")
        logger.info(f"Admin {ctx.author} unpaused quotes")

    async def _handle_blockchannel(self, ctx):
        """Block quotes in a channel"""
        if not ctx.message.channel_mentions:
            await ctx.send("Usage: `$quoteadmin blockchannel <#channel>`")
            return

        channel = ctx.message.channel_mentions[0]
        await self.bot.db.quote_ban_channel(channel.id, ctx.author.id)
        await ctx.send(f"Blocked quotes in {channel.mention}.")
        logger.info(f"Admin {ctx.author} blocked quotes in channel {channel.name} ({channel.id})")

    async def _handle_unblockchannel(self, ctx):
        """Unblock quotes in a channel"""
        if not ctx.message.channel_mentions:
            await ctx.send("Usage: `$quoteadmin unblockchannel <#channel>`")
            return

        channel = ctx.message.channel_mentions[0]
        success = await self.bot.db.quote_unban_channel(channel.id)
        if success:
            await ctx.send(f"Unblocked quotes in {channel.mention}.")
            logger.info(f"Admin {ctx.author} unblocked quotes in channel {channel.name} ({channel.id})")
        else:
            await ctx.send(f"{channel.mention} was not blocked.")

    async def _handle_status(self, ctx):
        """Show current quote restrictions"""
        db = self.bot.db

        # Pause state
        paused_until = await db.get_bot_setting('quote_paused_until')
        now = int(time.time())
        if paused_until and paused_until > now:
            pause_text = f"Paused until <t:{paused_until}:F> (<t:{paused_until}:R>)"
        else:
            pause_text = "Not paused"

        # Banned users
        async with db.pool.acquire() as conn:
            banned_users = await conn.fetch(
                'SELECT user_id, banned_by, banned_at FROM quote_banned_users ORDER BY banned_at DESC'
            )

        if banned_users:
            user_lines = [f"<@{r['user_id']}> (`{r['user_id']}`)" for r in banned_users[:15]]
            banned_text = "\n".join(user_lines)
        else:
            banned_text = "None"

        # Banned channels
        banned_channels = await db.get_quote_banned_channels()
        if banned_channels:
            channel_lines = [f"<#{r['channel_id']}> (`{r['channel_id']}`)" for r in banned_channels[:15]]
            channels_text = "\n".join(channel_lines)
        else:
            channels_text = "None"

        embed = Embed(
            title="Quote Admin Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="Pause State", value=pause_text, inline=False)
        embed.add_field(name=f"Banned Users ({len(banned_users)})", value=banned_text, inline=False)
        embed.add_field(name=f"Blocked Channels ({len(banned_channels)})", value=channels_text, inline=False)

        await ctx.send(embed=embed)
        logger.info(f"Admin {ctx.author} viewed quote admin status")
