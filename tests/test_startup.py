"""Regression coverage for startup and on_ready lifecycle."""

import runpy
from pathlib import Path
from types import SimpleNamespace

import discord
import pytest
from discord.ext.commands import Bot

import config
import logger
from db import Database


async def test_database_retry_exhaustion_aborts_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the final DB error and never connect to the gateway."""
    settings = SimpleNamespace(
        environment="test",
        prefix="$",
        owner_id=1,
        database_url="postgresql://unused",
        bot_token="unused",
        gemini_api_key=None,
    )
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    monkeypatch.setattr(logger, "setup_logging", lambda: None)
    # Load the entrypoint without invoking its blocking runner.
    monkeypatch.setattr(Bot, "run", lambda self, token: None)
    namespace = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "hablemos.py")
    )
    bot = namespace["bot"]
    failures: list[ConnectionError] = []
    delays: list[int] = []
    gateway_connected = False

    async def fail_connect(self: Database) -> None:
        error = ConnectionError(f"Database unavailable, attempt {len(failures) + 1}")
        failures.append(error)
        raise error

    async def skip_sleep(delay: int) -> None:
        delays.append(delay)

    async def login(token: str) -> None:
        # Bypass Discord HTTP authentication, not the startup hook.
        await bot.setup_hook()

    async def connect(*, reconnect: bool = True) -> None:
        nonlocal gateway_connected
        gateway_connected = True

    monkeypatch.setattr(Database, "connect", fail_connect)
    monkeypatch.setattr(bot, "login", login)
    monkeypatch.setattr(bot, "connect", connect)
    monkeypatch.setitem(
        bot.setup_hook.__func__.__globals__,
        "asyncio",
        SimpleNamespace(sleep=skip_sleep),
    )

    async with bot:
        with pytest.raises(ConnectionError) as caught:
            await bot.start("unused")

    assert len(failures) == 5
    assert caught.value is failures[-1]
    assert delays == [1, 2, 4, 8]
    assert not gateway_connected


async def test_on_ready_announces_online_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reconnect-driven on_ready must not spam the online channel."""
    settings = SimpleNamespace(
        environment="test",
        prefix="$",
        owner_id=1,
        database_url="postgresql://unused",
        bot_token="unused",
        gemini_api_key=None,
        bot_playground_guild_id=11,
        error_channel_id=22,
        online_channel_id=33,
    )
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    monkeypatch.setattr(logger, "setup_logging", lambda: None)
    monkeypatch.setattr(Bot, "run", lambda self, token: None)
    namespace = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "hablemos.py")
    )
    bot = namespace["bot"]

    sent: list[str] = []

    class FakeChannel(discord.abc.Messageable):
        async def send(self, content: str, **kwargs) -> None:
            sent.append(content)

        async def _get_channel(self):
            return self

    online = FakeChannel()
    guild = SimpleNamespace(
        get_channel=lambda channel_id: online if channel_id == 33 else None,
    )
    monkeypatch.setattr(bot, "get_guild", lambda guild_id: guild)
    presence_calls: list[object] = []

    async def fake_presence(*, activity=None):
        presence_calls.append(activity)

    monkeypatch.setattr(bot, "change_presence", fake_presence)

    await bot.on_ready()
    await bot.on_ready()

    assert sent == ["I'm online bra :smiling_imp:"]
    assert len(presence_calls) == 2


async def test_on_ready_missing_guild_is_nonfatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        environment="test",
        prefix="$",
        owner_id=1,
        database_url="postgresql://unused",
        bot_token="unused",
        gemini_api_key=None,
        bot_playground_guild_id=11,
        error_channel_id=22,
        online_channel_id=33,
    )
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    monkeypatch.setattr(logger, "setup_logging", lambda: None)
    monkeypatch.setattr(Bot, "run", lambda self, token: None)
    namespace = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "hablemos.py")
    )
    bot = namespace["bot"]
    monkeypatch.setattr(bot, "get_guild", lambda guild_id: None)

    await bot.on_ready()

    assert bot.online_channel is None
    assert bot.error_channel is None

