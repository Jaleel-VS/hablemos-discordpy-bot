"""Prefix-command errors reply once: BaseCog then ErrorHandler."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from discord.ext import commands

from base_cog import BaseCog
from cogs.error_handler_cog.main import ErrorHandler


@dataclass
class FakeCommand:
    qualified_name: str = "practice"
    signature: str = "[action]"
    checks: list[Any] = field(default_factory=list)


@dataclass
class FakeContext:
    prefix: str = "$"
    command: FakeCommand | None = field(default_factory=FakeCommand)
    channel: Any = field(default_factory=lambda: SimpleNamespace(id=1))
    author: Any = field(default_factory=lambda: SimpleNamespace(id=2))
    guild: Any = field(default_factory=lambda: SimpleNamespace(id=3))
    cog: Any = None
    message: Any = field(default_factory=lambda: SimpleNamespace(content="$practice"))
    sent: list[str] = field(default_factory=list)

    async def send(self, content: str) -> None:
        self.sent.append(content)


def _check_with_fail_msg(msg: str):
    def predicate(_ctx: Any) -> bool:
        return True

    predicate.fail_msg = msg
    return predicate


async def test_basecog_cooldown_sets_handled_and_replies_once() -> None:
    cog = BaseCog(cast(Any, SimpleNamespace()))
    ctx = FakeContext()
    error = commands.CommandOnCooldown(
        commands.Cooldown(1, 10), retry_after=4.2, type=commands.BucketType.user,
    )

    await cog.cog_command_error(ctx, error)

    assert ctx.sent == ["⏱️ Command is on cooldown. Try again in 4.2 seconds."]
    assert ctx.__dict__["error_handled"] is True


async def test_basecog_check_failure_uses_fail_msg() -> None:
    cog = BaseCog(cast(Any, SimpleNamespace()))
    ctx = FakeContext(command=FakeCommand(checks=[_check_with_fail_msg("Mods only.")]))

    await cog.cog_command_error(ctx, commands.CheckFailure())

    assert ctx.sent == ["Mods only."]
    assert ctx.__dict__["error_handled"] is True


async def test_basecog_missing_permissions_uses_generic_check_copy() -> None:
    cog = BaseCog(cast(Any, SimpleNamespace()))
    ctx = FakeContext()

    await cog.cog_command_error(ctx, commands.MissingPermissions(["manage_messages"]))

    assert ctx.sent == ["You don't have permission to use this command."]
    assert ctx.__dict__["error_handled"] is True



async def test_basecog_user_input_error_omits_raw_exception() -> None:
    cog = BaseCog(cast(Any, SimpleNamespace()))
    ctx = FakeContext()

    await cog.cog_command_error(ctx, commands.BadArgument("internal converter boom"))

    assert ctx.sent == ["Invalid input.\nUsage: `$practice [action]`"]
    assert "internal converter boom" not in ctx.sent[0]
    assert ctx.__dict__["error_handled"] is True

async def test_basecog_unexpected_error_does_not_claim_handled() -> None:
    cog = BaseCog(cast(Any, SimpleNamespace()))
    ctx = FakeContext()

    await cog.cog_command_error(ctx, RuntimeError("boom"))

    assert ctx.sent == []
    assert "error_handled" not in ctx.__dict__


async def test_error_handler_skips_user_reply_when_basecog_handled() -> None:
    db = SimpleNamespace(record_command=AsyncMock())
    bot = SimpleNamespace(db=db, command_prefix="$", settings=SimpleNamespace(league_guild_id=3))
    handler = ErrorHandler(cast(Any, bot))
    ctx = FakeContext()
    ctx.__dict__["error_handled"] = True

    await handler.on_command_error(ctx, commands.CommandOnCooldown(
        commands.Cooldown(1, 10), retry_after=1.0, type=commands.BucketType.user,
    ))

    assert ctx.sent == []
    db.record_command.assert_awaited_once()
    assert db.record_command.await_args.kwargs["failed"] is True


async def test_error_handler_unexpected_error_replies_once() -> None:
    db = SimpleNamespace(record_command=AsyncMock())
    bot = SimpleNamespace(
        db=db,
        command_prefix="$",
        settings=SimpleNamespace(league_guild_id=3),
    )
    handler = ErrorHandler(cast(Any, bot))
    ctx = FakeContext()

    await handler.on_command_error(
        ctx, commands.CommandInvokeError(RuntimeError("db down")),
    )

    assert ctx.sent == ["An unexpected error occurred. Please try again later."]
    db.record_command.assert_awaited_once()
