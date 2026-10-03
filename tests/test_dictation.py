"""Only one /dictation session may occupy a channel."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from cogs.dictation_cog.main import DictationCog


class _Choice:
    def __init__(self, value: str, name: str) -> None:
        self.value = value
        self.name = name


class _Response:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.deferred = False

    async def send_message(self, content: str, **_kwargs: Any) -> None:
        self.sent.append(content)

    async def defer(self) -> None:
        self.deferred = True
        await asyncio.sleep(0)


class _Followup:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str, **_kwargs: Any) -> None:
        self.sent.append(content)


@pytest.mark.asyncio
async def test_second_dictation_is_rejected_while_first_is_fetching() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_sentence(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        started.set()
        await release.wait()
        return {"id": 1, "sentence": "hola", "audio_url": "s3://x"}

    bot = SimpleNamespace(
        db=SimpleNamespace(get_random_dictation=slow_sentence, record_dictation_score=AsyncMock()),
        wait_for=AsyncMock(side_effect=TimeoutError),
    )
    cog = DictationCog(cast(Any, bot))
    cog._fetch_audio = AsyncMock(return_value=b"mp3")  # type: ignore[method-assign]

    first = SimpleNamespace(
        channel_id=9,
        user=SimpleNamespace(id=1),
        response=_Response(),
        followup=_Followup(),
        channel=SimpleNamespace(),
    )
    second = SimpleNamespace(
        channel_id=9,
        user=SimpleNamespace(id=2),
        response=_Response(),
        followup=_Followup(),
        channel=SimpleNamespace(),
    )
    lang = _Choice("es", "Spanish")
    level = _Choice("beginner", "Beginner")

    task = asyncio.create_task(DictationCog.dictation.callback(cog, first, lang, level))
    await started.wait()
    await DictationCog.dictation.callback(cog, second, lang, level)
    release.set()
    await task

    assert any("already a dictation" in msg for msg in second.response.sent)
    assert 9 not in cog._pending
