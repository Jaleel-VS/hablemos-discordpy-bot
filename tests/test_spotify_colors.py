"""Artwork fallback colors and the actual np2 image background."""

from collections.abc import AsyncIterator
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from PIL import Image

from cogs.spotify_cog.main import SpotifyCog, _dominant_color
from cogs.spotify_cog.renderer import render_nowplaying

CHARCOAL = (36, 38, 43)


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
async def artwork_server() -> AsyncIterator[str]:
    """Serve actual image bytes so palette extraction runs without HTTP mocks."""
    payloads = {
        "gray": _png((128, 128, 128)),
        "blue": _png((30, 70, 150)),
        "invalid": b"not an image",
    }

    async def image(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if name not in payloads:
            raise web.HTTPNotFound()
        return web.Response(body=payloads[name], content_type="image/png")

    app = web.Application()
    app.router.add_get("/{name}", image)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        yield f"http://127.0.0.1:{runner.addresses[0][1]}"
    finally:
        await runner.cleanup()


@pytest.mark.parametrize("artwork", ["gray", "missing", "invalid"])
async def test_unusable_artwork_returns_unmodified_charcoal(artwork_server: str, artwork: str) -> None:
    color = await _dominant_color(f"{artwork_server}/{artwork}")
    assert (color.r, color.g, color.b) == CHARCOAL
    image = await render_nowplaying("Track", "Artist", "Album", None, (color.r, color.g, color.b))
    with Image.open(image) as rendered:
        assert rendered.getpixel((1100, 380))[:3] == CHARCOAL


async def test_single_color_palette_is_not_mistaken_for_a_failed_image(artwork_server: str) -> None:
    color = await _dominant_color(f"{artwork_server}/blue")
    assert color.b > color.g > color.r
    assert (color.r, color.g, color.b) != CHARCOAL


async def test_renderer_without_an_accent_uses_charcoal() -> None:
    image = await render_nowplaying("Track", "Artist", "Album", None)
    with Image.open(image) as rendered:
        assert rendered.getpixel((1100, 380))[:3] == CHARCOAL


async def test_np2_missing_artwork_renders_charcoal() -> None:
    cog = SpotifyCog(SimpleNamespace())
    target = SimpleNamespace(display_name="Listener")
    spotify = SimpleNamespace(title="Track", artist="Artist", album="Album", album_cover_url=None, track_url=None)
    cog._listening_target = AsyncMock(return_value=(target, spotify))
    ctx = SimpleNamespace(send=AsyncMock())
    await cog.nowplaying_v2.callback(cog, ctx)
    file = ctx.send.await_args.kwargs["file"]
    try:
        with Image.open(file.fp) as rendered:
            assert rendered.getpixel((1100, 380))[:3] == CHARCOAL
    finally:
        file.close()
