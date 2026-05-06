"""Global command error handler cog."""
from __future__ import annotations

import difflib
import logging

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import red_embed, yellow_embed

logger = logging.getLogger(__name__)


class ErrorHandler(BaseCog):
    """Global command error handler."""

    @commands.Cog.listener()
    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Handle command errors that were not handled by a cog-level handler."""
        if getattr(ctx, "error_handled", False):
            return

        if self._should_ignore_non_command_prefix(ctx):
            return

        await self._record_failed_command(ctx)

        try:
            await self._dispatch_error(ctx, error)
            ctx.error_handled = True
        except discord.HTTPException:
            logger.debug(
                "Failed to send command error response",
                exc_info=True,
            )

    def _should_ignore_non_command_prefix(self, ctx: commands.Context) -> bool:
        """Return whether a prefixed message should be ignored as non-command noise."""
        content = getattr(ctx.message, "content", "")

        if len(content) <= 1:
            return False

        return (
            content[1].isdigit()
            or content[-1] == str(self.bot.command_prefix)
        )

    async def _record_failed_command(self, ctx: commands.Context) -> None:
        """Record a failed command metric without breaking error handling."""
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
            logger.debug("Failed to record failed command metric", exc_info=True)

    async def _dispatch_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Route a command error to its specific handler."""
        if isinstance(error, commands.CommandNotFound):
            await self._handle_command_not_found(ctx)
            return

        if isinstance(error, commands.CommandOnCooldown):
            await self._handle_cooldown(ctx, error)
            return

        if isinstance(error, (commands.MissingPermissions, commands.NotOwner)):
            await self._handle_permission_denied(ctx)
            return

        if isinstance(error, commands.CheckFailure):
            await self._handle_check_failure(ctx)
            return

        if isinstance(error, commands.UserInputError):
            # Usually handled by BaseCog.cog_command_error.
            # Keep silent here to avoid duplicate messages.
            return

        if (
            isinstance(error, commands.CommandInvokeError)
            and isinstance(error.original, discord.Forbidden)
        ):
            logger.debug("Forbidden error, likely blocked by user: %s", error.original)
            return

        await self._handle_unexpected_error(ctx, error)

    async def _handle_command_not_found(self, ctx: commands.Context) -> None:
        """Handle unknown commands with optional fuzzy suggestions."""
        if not ctx.guild or ctx.guild.id != self.bot.settings.league_guild_id:
            return

        invoked = ctx.invoked_with or ""
        all_commands = [command.name for command in self.bot.commands if not command.hidden]
        close_matches = difflib.get_close_matches(
            invoked,
            all_commands,
            n=3,
            cutoff=0.6,
        )

        if close_matches:
            suggestions = ", ".join(
                f"`{self.bot.command_prefix}{command}`"
                for command in close_matches
            )
            message = f"Command not found. Did you mean {suggestions}?"
        else:
            message = "Command not found."

        await ctx.send(
            embed=red_embed(
                message,
                title="Command not found",
            )
        )

        await self._log_command_not_found(ctx)

    async def _log_command_not_found(self, ctx: commands.Context) -> None:
    """Send redacted command-not-found details to the configured error channel."""
    error_channel = self.bot.error_channel

    if isinstance(error_channel, discord.TextChannel) and ctx.guild:
        await error_channel.send(
            "------\n"
            "Command not found:\n"
            f"Guild ID: {ctx.guild.id}\n"
            f"Channel ID: {ctx.channel.id}\n"
            f"Message length: {len(ctx.message.content)}\n"
            "Content: [redacted]\n"
            "------"
        )

    logger.warning(
        "Command not found | guild_id=%s | channel_id=%s | message_length=%s",
        ctx.guild.id if ctx.guild else "DM",
        ctx.channel.id,
        len(ctx.message.content),
    )
        logger.warning(
            "Command not found: %s | guild: %s (%s) | user: %s",
            ctx.message.content,
            ctx.guild.name if ctx.guild else "DM",
            ctx.guild.id if ctx.guild else "N/A",
            ctx.author.id,
        )

    async def _handle_cooldown(
        self,
        ctx: commands.Context,
        error: commands.CommandOnCooldown,
    ) -> None:
        """Handle command cooldown errors."""
        retry_after = round(error.retry_after)

        await ctx.send(
            embed=yellow_embed(
                (
                    "This command is on cooldown.\n"
                    f"Try again in `{retry_after}` seconds."
                ),
                title="Command on cooldown",
            )
        )

        logger.info("Command on cooldown: %s", ctx.message.content)

    async def _handle_permission_denied(self, ctx: commands.Context) -> None:
        """Handle missing permission and owner-only command errors."""
        owner_id = self.bot.settings.owner_id

        await ctx.send(
            embed=red_embed(
                (
                    "You do not have permission to use this command.\n\n"
                    f"If you think this is a mistake, contact <@{owner_id}>."
                ),
                title="Permission denied",
            )
        )

    async def _handle_check_failure(self, ctx: commands.Context) -> None:
        """Handle generic check failures."""
        message = self._get_check_fail_message(ctx)

        await ctx.send(
            embed=red_embed(
                message or "You do not have permission to use this command.",
                title="Permission denied",
            )
        )

    def _get_check_fail_message(self, ctx: commands.Context) -> str | None:
        """Return a custom fail message from command checks, if present."""
        if not ctx.command:
            return None

        for check in ctx.command.checks:
            if hasattr(check, "fail_msg"):
                return check.fail_msg

        return None

    async def _handle_unexpected_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Handle unexpected command errors."""
        logger.error(
            "Unhandled command error in command %s",
            ctx.command,
            exc_info=error,
        )

        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.send(
                embed=red_embed(
                    "An unexpected error occurred. Please try again later.",
                    title="Unexpected error",
                )
            )


async def setup(bot: commands.Bot) -> None:
    """Load the global error handler cog."""
    await bot.add_cog(ErrorHandler(bot))
