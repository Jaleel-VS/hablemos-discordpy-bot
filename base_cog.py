"""Base cog class shared by all cogs."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext.commands import (
    CheckFailure,
    Cog,
    CommandOnCooldown,
    CommandNotFound,
    MissingRequiredArgument,
    BadArgument,
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
                        "Este comando está en cooldown.\n"
                        f"Intenta nuevamente en `{error.retry_after:.1f}` segundos."
                    ),
                    title="Error de cooldown",
                )
            )

        elif isinstance(error, CheckFailure):
            msg = self._get_check_fail_message(ctx)
            await ctx.send(
                embed=red_embed(
                    msg or "No tienes permiso para usar este comando.",
                    title="Permiso denegado",
                )
            )

        elif isinstance(error, MissingRequiredArgument):
            await ctx.send(
                embed=red_embed(
                    self._format_usage(ctx),
                    title="Falta un argumento",
                )
            )

        elif isinstance(error, BadArgument):
            await ctx.send(
                embed=red_embed(
                    self._format_usage(ctx),
                    title="Argumento inválido",
                )
            )

        elif isinstance(error, UserInputError):
            await ctx.send(
                embed=red_embed(
                    self._format_usage(ctx),
                    title="Entrada inválida",
                )
            )

        else:
            logger.exception(
                "Unhandled command error in channel %s",
                getattr(ctx, "channel", None),
                exc_info=error,
            )
            await ctx.send(
                embed=red_embed(
                    "Ocurrió un error interno al ejecutar el comando.",
                    title="Error interno",
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
            return "La entrada entregada no es válida."

        signature = ctx.command.signature
        command_name = ctx.command.qualified_name
        usage = f"{ctx.prefix}{command_name}"

        if signature:
            usage = f"{usage} {signature}"

        return (
            "La entrada entregada no es válida.\n\n"
            f"Uso correcto:\n`{usage}`"
        )
