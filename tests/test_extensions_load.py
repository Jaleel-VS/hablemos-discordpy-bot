"""Every code-enabled extension loads at startup against a real schema.

`setup_hook` logs and skips a cog that fails to load, so a broken cog
would otherwise only show up as missing commands in production.
Skipped unless TEST_DATABASE_URL points at a server where the user can
create databases.
"""
import os
import sys
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from cogs.utils.discovery import discover_extensions, is_code_enabled
from config import load_settings
from hablemos import Hablemos


async def test_every_enabled_extension_loads(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to run the extension load test")
    name = "cog_load_test_" + uuid4().hex
    admin = await asyncpg.connect(url)
    await admin.execute(f'CREATE DATABASE "{name}"')
    monkeypatch.setenv("BOT_TOKEN", "unused")
    monkeypatch.setenv("DATABASE_URL", urlunsplit(urlsplit(url)._replace(path="/" + name)))
    monkeypatch.setenv("GEMINI_API_KEY", "unused")
    bot = Hablemos("$", load_settings())
    # load_extension re-executes each cog module into sys.modules; put the
    # originals back so later tests patch the modules their objects came from.
    modules = dict(sys.modules)
    try:
        async with bot:
            await bot.setup_hook()
            expected = {ext for ext in discover_extensions() if is_code_enabled(ext)}
            failures = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
            loaded = set(bot.extensions)
            for ext in list(bot.extensions):
                await bot.unload_extension(ext)
        assert loaded == expected, failures
    finally:
        sys.modules.update(modules)
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()
