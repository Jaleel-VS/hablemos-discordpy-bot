"""Reply-target resolution for interaction recording."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.interactions_cog.main import InteractionsCog


async def _resolve(**kwargs: Any) -> discord.abc.User | None:
    return await InteractionsCog._author_from_reference(**kwargs)


@pytest.mark.asyncio
async def test_uncached_reply_fetches_author() -> None:
    author = SimpleNamespace(id=9, bot=False)
    fetch = AsyncMock(return_value=SimpleNamespace(author=author))

    result = await _resolve(
        resolved=None,
        message_id=42,
        ref_type=discord.MessageReferenceType.reply,
        fetch=fetch,
    )

    assert result is author
    fetch.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_cached_reply_does_not_fetch() -> None:
    author = SimpleNamespace(id=9, bot=False)
    fetch = AsyncMock()

    result = await _resolve(
        resolved=SimpleNamespace(author=author),
        message_id=42,
        ref_type=discord.MessageReferenceType.reply,
        fetch=fetch,
    )

    assert result is author
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_forwarded_reference_is_ignored() -> None:
    fetch = AsyncMock()

    result = await _resolve(
        resolved=None,
        message_id=42,
        ref_type=discord.MessageReferenceType.forward,
        fetch=fetch,
    )

    assert result is None
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_referenced_message_is_ignored() -> None:
    class _NotFound(discord.NotFound):
        def __init__(self) -> None:
            Exception.__init__(self, "gone")

    fetch = AsyncMock(side_effect=_NotFound())

    result = await _resolve(
        resolved=None,
        message_id=42,
        ref_type=discord.MessageReferenceType.reply,
        fetch=fetch,
    )

    assert result is None


@pytest.mark.asyncio
async def test_deleted_referenced_message_is_ignored() -> None:
    fetch = AsyncMock()
    resolved = object.__new__(discord.DeletedReferencedMessage)

    result = await _resolve(
        resolved=resolved,
        message_id=42,
        ref_type=discord.MessageReferenceType.reply,
        fetch=fetch,
    )

    assert result is None
    fetch.assert_not_awaited()
