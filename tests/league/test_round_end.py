"""Round end switches scoring to the new round before the Discord work."""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from cogs.league_cog.levels import XpGain
from cogs.league_cog.main import LeagueCog
from cogs.utils.guild import HOME_GUILD_ID

OLD_ROUND = {
    'round_id': 1,
    'round_number': 7,
    'start_date': datetime.now(UTC) - timedelta(days=7),
    'end_date': datetime.now(UTC) - timedelta(minutes=1),
    'status': 'active',
}
NEW_ROUND_ID = 2
LEARNER_ID = 100


@dataclass
class FakeDB:
    recorded_round_ids: list[int] = field(default_factory=list)

    async def get_current_round(self) -> dict:
        return OLD_ROUND

    async def get_all_opted_in_users(self) -> list[dict]:
        return [{'user_id': LEARNER_ID, 'learning_spanish': True, 'learning_english': False}]

    async def get_all_banned_users(self) -> list[dict]:
        return []

    async def get_excluded_channels(self) -> list[dict]:
        return []

    async def get_last_round_role_recipients(self) -> set[int]:
        return set()

    async def get_leaderboard(self, board: str, limit: int, round_id: int) -> list[dict]:
        return []

    async def complete_round(self, *_args) -> int:
        return NEW_ROUND_ID

    async def record_activity(self, *, round_id: int, **_kwargs) -> XpGain:
        self.recorded_round_ids.append(round_id)
        return XpGain(xp_before=0, xp_after=1, cards_enabled=True)


@dataclass
class Author:
    id: int
    bot: bool = False


@dataclass
class Guild:
    id: int


@dataclass
class Channel:
    id: int


@dataclass
class Message:
    author: Author
    guild: Guild
    channel: Channel
    content: str
    id: int = 1


@dataclass
class WinnerChannel:
    """Delivers a learner's message while the announcement is being sent."""

    cog: LeagueCog | None = None

    async def send(self, *_args, **_kwargs) -> None:
        assert self.cog is not None
        await self.cog.on_message(Message(  # type: ignore[arg-type]
            author=Author(LEARNER_ID),
            guild=Guild(HOME_GUILD_ID),
            channel=Channel(555),
            content="Hoy hace muy buen tiempo y quiero salir a caminar por el parque.",
        ))


@dataclass
class FakeBot:
    db: FakeDB
    channel: WinnerChannel
    persistent_views: list = field(default_factory=list)
    _never_ready: asyncio.Event = field(default_factory=asyncio.Event)

    def add_view(self, view) -> None:
        self.persistent_views.append(view)

    async def wait_until_ready(self) -> None:
        await self._never_ready.wait()

    def get_guild(self, _guild_id: int) -> None:
        return None

    def get_channel(self, _channel_id: int) -> WinnerChannel:
        return self.channel

    def get_user(self, _user_id: int) -> None:
        return None


async def test_message_during_announcement_scores_in_new_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "cogs.league_cog.rounds.render_round_end", lambda **_kwargs: io.BytesIO(b"png"),
    )
    db = FakeDB()
    channel = WinnerChannel()
    cog = LeagueCog(FakeBot(db=db, channel=channel))  # type: ignore[arg-type]
    channel.cog = cog
    try:
        await cog.cog_load()
        result = await cog._process_round_end(OLD_ROUND)
    finally:
        cog.cog_unload()

    assert result is not None
    assert db.recorded_round_ids == [NEW_ROUND_ID]
