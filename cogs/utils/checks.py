"""Reusable command checks for permission gating."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from discord import Member

logger = logging.getLogger(__name__)


def min_role(role_id: int):
    """Require the minimum role, or Manage Messages if the role is unconfigured/missing."""

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        member: Member = ctx.author  # type: ignore[assignment]

        if role_id == 0:
            return _check_manage_messages(member)

        role = ctx.guild.get_role(role_id)
        if role is None:
            logger.warning(
                "min_role check: role %s not found in guild %s, "
                "falling back to Manage Messages permission",
                role_id, ctx.guild.id,
            )
            return _check_manage_messages(member)

        if member.top_role >= role:
            return True

        raise commands.MissingRole(role.name)

    return commands.check(predicate)


def _check_manage_messages(member: Member) -> bool:
    if member.guild_permissions.manage_messages:
        return True
    raise commands.MissingPermissions(["manage_messages"])
