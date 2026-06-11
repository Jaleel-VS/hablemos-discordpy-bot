"""Handwritten fakes for World Cup betting panel tests.

Mirrors the crossword test harness style (`tests/crossword/conftest.py`):
no mocks — small recording fakes for the DB, bot, and interaction, plus a
frozen clock injected through the `views._now_utc` seam.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from cogs.wcbet_cog import views

USER_ID = 42
GUILD_ID = 1


class FakeDB:
    """Records betting DB calls; returns canned wallet/bet rows."""

    def __init__(self) -> None:
        self.wallet: dict[str, Any] | None = {
            "user_id": USER_ID,
            "guild_id": GUILD_ID,
            "balance": 10_000,
            "last_allowance_date": None,
        }
        self.user_bets: dict[int, dict[str, Any]] = {}  # match_id -> pending bet row
        self.place_calls: list[dict[str, Any]] = []
        self.place_result: int = 9_500
        self.place_error: Exception | None = None
        self.created_wallets: list[tuple[int, int, int]] = []
        self.allowance_result: int | None = None

    async def get_wc_wallet(self, user_id: int) -> dict[str, Any] | None:
        return self.wallet

    async def create_wc_wallet(
        self, user_id: int, guild_id: int, starting_balance: int,
    ) -> bool:
        self.created_wallets.append((user_id, guild_id, starting_balance))
        return True

    async def claim_wc_daily_allowance(
        self, user_id: int, amount: int, today: Any,
    ) -> int | None:
        return self.allowance_result

    async def get_wc_user_bet(self, user_id: int, match_id: int) -> dict[str, Any] | None:
        return self.user_bets.get(match_id)

    async def get_wc_user_bets(
        self, user_id: int, status: str | None = None,
    ) -> list[dict[str, Any]]:
        return list(self.user_bets.values())

    async def place_wc_bet(
        self,
        user_id: int,
        guild_id: int,
        match_id: int,
        outcome: str,
        stake: int,
        odds: float,
    ) -> int:
        self.place_calls.append({
            "user_id": user_id,
            "guild_id": guild_id,
            "match_id": match_id,
            "outcome": outcome,
            "stake": stake,
            "odds": odds,
        })
        if self.place_error is not None:
            raise self.place_error
        return self.place_result


class FakeBot:
    """Minimal stand-in for commands.Bot — only `.db` is touched."""

    def __init__(self) -> None:
        self.db = FakeDB()


@dataclass
class FakeUser:
    id: int = USER_ID

    def __str__(self) -> str:
        return f"user-{self.id}"


class FakeResponse:
    """Captures interaction response calls."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.modals: list[Any] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)

    async def edit_message(self, **kwargs: Any) -> None:
        self.edited.append(kwargs)

    async def send_modal(self, modal: Any) -> None:
        self.modals.append(modal)


@dataclass
class FakeInteraction:
    user: FakeUser = field(default_factory=FakeUser)
    guild: Any = None  # None -> views skip channel logging
    guild_id: int = GUILD_ID
    response: FakeResponse = field(default_factory=FakeResponse)
    client: Any = None


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def interaction() -> FakeInteraction:
    return FakeInteraction()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    """Freeze `views._now_utc`; mutate ``holder['now']`` to advance time.

    Default: 2026-06-11 16:00 UTC (noon ET) — opening day, before any
    kickoff, so match 1 (19:00 UTC) and match 2 (02:00 UTC next day)
    are both bettable.
    """
    holder = {"now": datetime(2026, 6, 11, 16, 0, tzinfo=UTC)}
    monkeypatch.setattr(views, "_now_utc", lambda: holder["now"])
    return holder


@pytest.fixture(autouse=True)
def fake_odds(monkeypatch: pytest.MonkeyPatch) -> dict[int, Any]:
    """Stub the ESPN odds fetch — tests never touch the network.

    Empty by default (panel falls back to flat odds); tests insert
    `match_id -> MatchOdds` entries to simulate live DraftKings lines.
    """
    holder: dict[int, Any] = {}

    async def fetch(fixtures: list) -> dict[int, Any]:
        return {
            f["match_id"]: holder[f["match_id"]]
            for f in fixtures
            if f["match_id"] in holder
        }

    monkeypatch.setattr(views.espn, "fetch_match_odds", fetch)
    return holder
