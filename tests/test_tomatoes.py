"""Tomato command reports missing targets and renders explicitly mentioned users."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from cogs.tomatoes_cog.main import TomatoesCog


@pytest.mark.asyncio
async def test_tomato_without_target_sends_usage_hint() -> None:
    cog = TomatoesCog.__new__(TomatoesCog)
    ctx = SimpleNamespace(
        message=SimpleNamespace(mentions=[], reference=None),
        send=AsyncMock(), channel=SimpleNamespace(id=1), guild=None,
    )
    await cog.tomato.callback(cog, ctx)
    assert "$help tomato" in ctx.send.call_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_tomato_prefers_explicit_mention_and_removes_temporary_output(monkeypatch) -> None:
    avatar = BytesIO()
    Image.new("RGB", (2, 2)).save(avatar, format="PNG")
    asset = SimpleNamespace(read=AsyncMock(return_value=avatar.getvalue()))
    mentioned = SimpleNamespace(mention="<@1>", display_avatar=SimpleNamespace(with_size=lambda _size: asset))
    ctx = SimpleNamespace(
        message=SimpleNamespace(
            content="$tomato <@1>", mentions=[mentioned],
            reference=SimpleNamespace(resolved=SimpleNamespace(author=SimpleNamespace(mention="<@2>"))),
        ),
        send=AsyncMock(), channel=SimpleNamespace(id=1), guild=None,
    )
    paths = []

    def render(_image, path):
        from pathlib import Path
        Path(path).write_bytes(b"rendered animation")
        paths.append(Path(path))
        return path

    monkeypatch.setattr("cogs.tomatoes_cog.main.generate_tomatoes", render)
    cog = TomatoesCog.__new__(TomatoesCog)
    await cog.tomato.callback(cog, ctx)
    assert ctx.send.call_args.kwargs["content"] == "<@1>"
    assert ctx.send.call_args.kwargs["file"].filename.endswith(".webp")
    assert not paths[0].exists()
