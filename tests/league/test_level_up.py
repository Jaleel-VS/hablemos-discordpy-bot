"""A counted message that crosses a level threshold gets a level-up card reply."""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from cogs.league_cog.levels import XpGain, xp_for_level
from cogs.league_cog.main import LeagueCog
from cogs.utils.guild import HOME_GUILD_ID

LEARNER_ID = 100
ROUND = {
    'round_id': 1,
    'round_number': 1,
    'start_date': datetime.now(UTC),
    'end_date': datetime.now(UTC) + timedelta(days=7),
    'status': 'active',
}


@dataclass
class FakeDB:
    xp: int
    cards_enabled: bool = True

    async def get_current_round(self) -> dict:
        return ROUND

    async def get_all_opted_in_users(self) -> list[dict]:
        return [{'user_id': LEARNER_ID, 'learning_spanish': True, 'learning_english': False}]

    async def get_all_banned_users(self) -> list[dict]:
        return []

    async def get_excluded_channels(self) -> list[dict]:
        return []

    async def record_activity(self, *, points: int, **_kwargs) -> XpGain:
        self.xp += points
        return XpGain(self.xp - points, self.xp, self.cards_enabled)


@dataclass
class Asset:
    url: str = "https://cdn.example/avatar.png"

    def with_size(self, _size: int) -> Asset:
        return self


@dataclass
class Author:
    id: int = LEARNER_ID
    bot: bool = False
    display_avatar: Asset = field(default_factory=Asset)


@dataclass
class Guild:
    id: int = HOME_GUILD_ID


@dataclass
class Channel:
    id: int = 555


@dataclass
class Message:
    content: str = "Hoy hace muy buen tiempo y quiero salir a caminar por el parque."
    author: Author = field(default_factory=Author)
    guild: Guild = field(default_factory=Guild)
    channel: Channel = field(default_factory=Channel)
    id: int = 1
    replies: list[dict] = field(default_factory=list)

    async def reply(self, **kwargs) -> None:
        self.replies.append(kwargs)


@dataclass
class FakeBot:
    db: FakeDB
    persistent_views: list = field(default_factory=list)
    _never_ready: asyncio.Event = field(default_factory=asyncio.Event)

    def add_view(self, view) -> None:
        self.persistent_views.append(view)

    async def wait_until_ready(self) -> None:
        await self._never_ready.wait()


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    calls: list[tuple] = []

    def fake_render(old_level, progress, avatar_url) -> io.BytesIO:
        calls.append((old_level, progress.level, avatar_url))
        return io.BytesIO(b"png")

    monkeypatch.setattr("cogs.league_cog.main.render_level_up", fake_render)
    return calls


async def _send(db: FakeDB) -> Message:
    cog = LeagueCog(FakeBot(db))  # type: ignore[arg-type]
    message = Message()
    try:
        await cog.cog_load()
        await cog.on_message(message)  # type: ignore[arg-type]
    finally:
        cog.cog_unload()
    return message


async def test_crossing_a_threshold_replies_with_a_card(rendered: list[tuple]) -> None:
    message = await _send(FakeDB(xp=xp_for_level(2) - 1))

    assert rendered == [(1, 2, "https://cdn.example/avatar.png")]
    assert len(message.replies) == 1
    assert message.replies[0]["mention_author"] is False


async def test_no_card_without_a_level_up_or_with_cards_off(rendered: list[tuple]) -> None:
    within_level = await _send(FakeDB(xp=0))
    cards_off = await _send(FakeDB(xp=xp_for_level(2) - 1, cards_enabled=False))

    assert rendered == []
    assert within_level.replies == []
    assert cards_off.replies == []
