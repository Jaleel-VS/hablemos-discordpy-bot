"""Base cog class shared by all cogs."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext.commands import (
    BadArgument,
    CheckFailure,
    Cog,
    CommandNotFound,
    CommandOnCooldown,
    MissingRequiredArgument,
    UserInputError,
)

from cogs.utils.embeds import red_embed

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


class BaseCog(Cog):
    """Base class for all cogs."""

    def __init__(self, bot: Hablemos):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        """Handle errors for commands in this cog."""
        if getattr(ctx, "error_handled", False):
            return

        error = getattr(error, "original", error)

        if isinstance(error, CommandNotFound):
            return

        if isinstance(error, CommandOnCooldown):
            await ctx.send(
                embed=red_embed(
                    (
                        "This command is on cooldown.\n"
                        f"Try again in `{error.retry_after:.1f}` seconds."
                    ),
                    title="Command on cooldown",
                )
            )

        elif isinstance(error, CheckFailure):
            msg = self._get_check_fail_message(ctx)
            await ctx.send(
                embed=red_embed(
                    msg or "You do not have permission to use this command.",
                    title="Permission denied",
                )
            )

        elif isinstance(error, MissingRequiredArgument):
            await ctx.send(
                embed=red_embed(
                    self._format_usage(ctx),
                    title="Missing required argument",
                )
            )

        elif isinstance(error, BadArgument):
            await ctx.send(
                embed=red_embed(
                    self._format_usage(ctx),
                    title="Invalid argument",
                )
            )

        elif isinstance(error, UserInputError):
            await ctx.send(
                embed=red_embed(
                    self._format_usage(ctx),
                    title="Invalid input",
                )
            )

        else:
            logger.error(
                "Unhandled command error in channel %s",
                getattr(ctx, "channel", None),
                exc_info=error,
            )
            await ctx.send(
                embed=red_embed(
                    "An internal error occurred while running this command.",
                    title="Internal error",
                )
            )
            ctx.error_handled = True
            raise error

        ctx.error_handled = True

    def _get_check_fail_message(self, ctx) -> str | None:
        """Return custom fail message from command checks, if present."""
        if not ctx.command:
            return None

        for check in ctx.command.checks:
            if hasattr(check, "fail_msg"):
                return check.fail_msg

        return None

    def _format_usage(self, ctx) -> str:
        """Return a safe usage message for invalid command input."""
        if not ctx.command:
            return "The provided input is invalid."

        signature = ctx.command.signature
        command_name = ctx.command.qualified_name
        usage = f"{ctx.prefix}{command_name}"

        if signature:
            usage = f"{usage} {signature}"

        return (
            "The provided input is invalid.\n\n"
            f"Correct usage:\n`{usage}`"
        )
