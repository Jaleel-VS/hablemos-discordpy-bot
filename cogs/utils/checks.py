"""Reusable command checks for permission gating."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from discord import Member

logger = logging.getLogger(__name__)


def min_role(
    role_id: int,
    *,
    fallback: str = "manage_messages",
):
    """Restrict a command to members whose top role is at or above *role_id*.

    Parameters
    ----------
    role_id:
        The Discord role ID representing the minimum required role.
        If ``0``, the check falls back to a permission check.
    fallback:
        Permission name to check when the role is not configured (0) or
        cannot be found in the guild.  Defaults to ``"manage_messages"``.

    Behaviour
    ---------
    - ``role_id == 0`` → fall back to *fallback* permission.
    - Role not found in guild (deleted/misconfigured) → log warning, fall
      back to *fallback* permission.
    - Role found → require ``member.top_role >= role``.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        member: Member = ctx.author  # type: ignore[assignment]

        # Not configured — use fallback permission
        if role_id == 0:
            return _check_fallback(member, fallback)

        role = ctx.guild.get_role(role_id)
        if role is None:
            logger.warning(
                "min_role check: role %s not found in guild %s, "
                "falling back to '%s' permission",
                role_id, ctx.guild.id, fallback,
            )
            return _check_fallback(member, fallback)

        if member.top_role >= role:
            return True

        raise commands.MissingRole(role.name)

    return commands.check(predicate)


def _check_fallback(member: Member, permission: str) -> bool:
    """Check a single guild permission on the member."""
    perms = member.guild_permissions
    if getattr(perms, permission, False):
        return True
    raise commands.MissingPermissions([permission])
