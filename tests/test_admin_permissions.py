"""Permission checks for moderator-facing admin commands."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import discord
import pytest
from discord.ext import commands

from cogs.admin_cog.main import AdminCog


@dataclass
class FakeContext:
    """Minimal context exposing effective channel permissions."""

    permissions: discord.Permissions


def _fetch_permission_check() -> Any:
    return AdminCog.fetch_messages.checks[0]


def test_fetch_allows_manage_messages() -> None:
    ctx = FakeContext(discord.Permissions(manage_messages=True))

    assert _fetch_permission_check()(cast(commands.Context, ctx)) is True


def test_fetch_rejects_missing_manage_messages() -> None:
    ctx = FakeContext(discord.Permissions.none())

    with pytest.raises(commands.MissingPermissions) as exc_info:
        _fetch_permission_check()(cast(commands.Context, ctx))

    assert exc_info.value.missing_permissions == ["manage_messages"]
