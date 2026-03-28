"""Quote admin commands — ban/unban users, pause quotes, block channels."""
import discord
from discord.ext import commands
from discord import Embed
from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed, yellow_embed
import logging
import re
import time

logger = logging.getLogger(__name__)

DURATION_PATTERN = re.compile(r'^(\d+)([mhd])$')
DURATION_MULTIPLIERS = {'m': 60, 'h': 3600, 'd': 86400}


def parse_duration(text: str) -> int | None:
    """Parse a duration string like 30m, 2h, 1d into seconds. Returns None if invalid."""
    match = DURATION_PATTERN.match(text.strip().lower())
    if not match:
        return None
    return int(match.group(1)) * DURATION_MULTIPLIERS[match.group(2)]


def _resolve_user_id(ctx, target: str | None) -> int | None:
    """Extract a user ID from mentions or raw input. Returns None if invalid."""
    if not target:
        return None
    if ctx.message.mentions:
        return ctx.message.mentions[0].id
    try:
        return int(target.strip())
    except ValueError:
        return None


class QuoteAdminCog(BaseCog):
    """Admin-only commands for quote management."""

    @commands.group(name='quoteadmin', invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def quoteadmin(self, ctx: commands.Context):
        """Quote admin management. Subcommands: ban, unban, pause, unpause, blockchannel, unblockchannel, status."""
        await ctx.send(embed=red_embed(
            "Usage: `$quoteadmin <ban|unban|pause|unpause|blockchannel|unblockchannel|status> [target]`"
        ))

    @quoteadmin.command(name='ban')
    @commands.has_permissions(manage_messages=True)
    async def ban(self, ctx: commands.Context, *, target: str = None):
        """Ban a user from using quote commands."""
        user_id = _resolve_user_id(ctx, target)
        if user_id is None:
            await ctx.send(embed=red_embed("Usage: `$quoteadmin ban <@user|user_id>`"))
            return
        await self.bot.db.quote_ban_user(user_id, ctx.author.id)
        await ctx.send(embed=green_embed(f"Banned user `{user_id}` from quote commands."))
        logger.info(f"{ctx.author} quote-banned user {user_id}")

    @quoteadmin.command(name='unban')
    @commands.has_permissions(manage_messages=True)
    async def unban(self, ctx: commands.Context, *, target: str = None):
        """Unban a user from quote commands."""
        user_id = _resolve_user_id(ctx, target)
        if user_id is None:
            await ctx.send(embed=red_embed("Usage: `$quoteadmin unban <@user|user_id>`"))
            return
        success = await self.bot.db.quote_unban_user(user_id)
        if success:
            await ctx.send(embed=green_embed(f"Unbanned user `{user_id}` from quote commands."))
            logger.info(f"{ctx.author} quote-unbanned user {user_id}")
        else:
            await ctx.send(embed=yellow_embed(f"User `{user_id}` was not banned."))

    @quoteadmin.command(name='pause')
    @commands.has_permissions(manage_messages=True)
    async def pause(self, ctx: commands.Context, duration: str = None):
        """Pause all quote usage for a duration (e.g. 30m, 2h, 1d)."""
        if not duration:
            await ctx.send(embed=red_embed("Usage: `$quoteadmin pause <duration>` (e.g. `30m`, `2h`, `1d`)"))
            return
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(embed=red_embed("Invalid duration. Use format like `30m`, `2h`, or `1d`."))
            return
        paused_until = int(time.time()) + seconds
        await self.bot.db.set_bot_setting('quote_paused_until', paused_until)
        await ctx.send(embed=green_embed(f"Quotes paused until <t:{paused_until}:F> (<t:{paused_until}:R>)."))
        logger.info(f"{ctx.author} paused quotes until {paused_until}")

    @quoteadmin.command(name='unpause')
    @commands.has_permissions(manage_messages=True)
    async def unpause(self, ctx: commands.Context):
        """Unpause quotes immediately."""
        await self.bot.db.set_bot_setting('quote_paused_until', 0)
        await ctx.send(embed=green_embed("Quotes have been unpaused."))
        logger.info(f"{ctx.author} unpaused quotes")

    @quoteadmin.command(name='blockchannel')
    @commands.has_permissions(manage_messages=True)
    async def blockchannel(self, ctx: commands.Context):
        """Block quotes in a channel."""
        if not ctx.message.channel_mentions:
            await ctx.send(embed=red_embed("Usage: `$quoteadmin blockchannel #channel`"))
            return
        channel = ctx.message.channel_mentions[0]
        await self.bot.db.quote_ban_channel(channel.id, ctx.author.id)
        await ctx.send(embed=green_embed(f"Blocked quotes in {channel.mention}."))
        logger.info(f"{ctx.author} blocked quotes in {channel.name} ({channel.id})")

    @quoteadmin.command(name='unblockchannel')
    @commands.has_permissions(manage_messages=True)
    async def unblockchannel(self, ctx: commands.Context):
        """Unblock quotes in a channel."""
        if not ctx.message.channel_mentions:
            await ctx.send(embed=red_embed("Usage: `$quoteadmin unblockchannel #channel`"))
            return
        channel = ctx.message.channel_mentions[0]
        success = await self.bot.db.quote_unban_channel(channel.id)
        if success:
            await ctx.send(embed=green_embed(f"Unblocked quotes in {channel.mention}."))
            logger.info(f"{ctx.author} unblocked quotes in {channel.name} ({channel.id})")
        else:
            await ctx.send(embed=yellow_embed(f"{channel.mention} was not blocked."))

    @quoteadmin.command(name='status')
    @commands.has_permissions(manage_messages=True)
    async def status(self, ctx: commands.Context):
        """Show current quote restrictions."""
        db = self.bot.db

        paused_until = await db.get_bot_setting('quote_paused_until')
        now = int(time.time())
        if paused_until and paused_until > now:
            pause_text = f"Paused until <t:{paused_until}:F> (<t:{paused_until}:R>)"
        else:
            pause_text = "Not paused"

        banned_users = await db.get_quote_banned_users()
        if banned_users:
            user_lines = [f"<@{r['user_id']}> (`{r['user_id']}`)" for r in banned_users[:15]]
            banned_text = "\n".join(user_lines)
        else:
            banned_text = "None"

        banned_channels = await db.get_quote_banned_channels()
        if banned_channels:
            channel_lines = [f"<#{r['channel_id']}> (`{r['channel_id']}`)" for r in banned_channels[:15]]
            channels_text = "\n".join(channel_lines)
        else:
            channels_text = "None"

        embed = Embed(title="Quote Admin Status", color=discord.Color.blue())
        embed.add_field(name="Pause State", value=pause_text, inline=False)
        embed.add_field(name=f"Banned Users ({len(banned_users)})", value=banned_text, inline=False)
        embed.add_field(name=f"Blocked Channels ({len(banned_channels)})", value=channels_text, inline=False)
        await ctx.send(embed=embed)
