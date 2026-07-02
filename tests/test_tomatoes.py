"""Regression test for the `$tomato` early-return UnboundLocalError.

`tomato` assigns `output_path` inside its try block, but the `finally`
clause references it unconditionally. Any path that returns (or raises)
before the assignment — most commonly the "no user supplied" early
return — used to crash with `UnboundLocalError` in `finally`. The fix
initializes `output_path = None` up front; this test pins that behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from cogs.tomatoes_cog.main import TomatoesCog


@dataclass
class FakeMessage:
    mentions: list = field(default_factory=list)
    reference: Any = None


@dataclass
class FakeChannel:
    id: int = 1


@dataclass
class FakeContext:
    """Minimal Context: no mentions, no reply -> the early-return path."""

    message: FakeMessage = field(default_factory=FakeMessage)
    channel: FakeChannel = field(default_factory=FakeChannel)
    guild: Any = None
    sent: list = field(default_factory=list)

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


@pytest.mark.asyncio
async def test_tomato_no_user_does_not_raise_unbound_output_path() -> None:
    cog = TomatoesCog.__new__(TomatoesCog)  # skip BaseCog __init__ (needs a bot)
    ctx = FakeContext()

    # Invoke the command's underlying coroutine directly. Before the fix this
    # raised UnboundLocalError from the finally block; now it returns cleanly
    # after sending the usage hint.
    callback = cast(Any, cog.tomato.callback)  # bound command callback (test)
    await callback(cog, ctx)

    assert ctx.sent, "should send a usage hint when no user is supplied"
