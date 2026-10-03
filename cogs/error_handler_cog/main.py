"""Global command error handler cog."""
from __future__ import annotations

import difflib
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class ErrorHandler(BaseCog):
    """Global command error handler."""

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Ignore non-command prefixes (e.g. "$5", "$$")
        if len(ctx.message.content) > 1 and (
            ctx.message.content[1].isdigit() or ctx.message.content[-1] == self.bot.command_prefix
        ):
            return

        # Record failed command metric even when BaseCog already replied.
        try:
            cog_name = type(ctx.cog).__name__ if ctx.cog else None
            await self.bot.db.record_command(
                command_name=str(ctx.command),
                cog_name=cog_name,
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                channel_id=ctx.channel.id,
                is_slash=False,
                failed=True,
            )
        except Exception:
            pass

        if getattr(ctx, 'error_handled', False):
            return

        try:
            if isinstance(error, commands.CommandNotFound):
                # Only handle command-not-found in the main server
                if not ctx.guild or ctx.guild.id != self.bot.settings.league_guild_id:
                    return

                # Suggest similar commands via fuzzy match
                invoked = ctx.invoked_with
                all_cmds = [c.name for c in self.bot.commands if not c.hidden]
                close = (
                    difflib.get_close_matches(invoked, all_cmds, n=3, cutoff=0.6)
                    if invoked is not None
                    else []
                )
                if close:
                    suggestions = ", ".join(f"`{self.bot.command_prefix}{c}`" for c in close)
                    await ctx.send(f"Command not found. Did you mean {suggestions}?")

                error_channel = self.bot.error_channel
                if isinstance(error_channel, discord.TextChannel) and ctx.guild:
                    await error_channel.send(
                        f"------\nCommand not found:\n{ctx.author}, {ctx.author.id}, {ctx.channel}, {ctx.channel.id}, "
                        f"{ctx.guild}, {ctx.guild.id}, \n{ctx.message.content}\n{ctx.message.jump_url}\n------"
                    )
                logger.warning(
                    "Command not found: %s | guild: %s (%s) | user: %s",
                    ctx.message.content,
                    ctx.guild.name if ctx.guild else "DM",
                    ctx.guild.id if ctx.guild else "N/A",
                    ctx.author.id,
                )

            elif isinstance(error, (commands.CommandOnCooldown, commands.CheckFailure, commands.UserInputError)):
                # Expected failures are answered by BaseCog.cog_command_error.
                return

            else:
                # Silently drop Forbidden from users who blocked the bot
                if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
                    logger.debug("Forbidden error (likely blocked): %s", error.original)
                    return
                logger.error("Unhandled error in command %s", ctx.command, exc_info=error)
                await ctx.send("An unexpected error occurred. Please try again later.")
        except discord.HTTPException:
            pass


async def setup(bot: Hablemos):
    await bot.add_cog(ErrorHandler(bot))
