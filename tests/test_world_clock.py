"""Tests for the world clock: zone parsing, card building, rendering, actions.

No Discord connection or database: zones and board are pure, the renderer is
a function of its cards, and actions and views run against in-memory fakes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest
from PIL import Image

from cogs.worldclock_cog import actions, board, renderer, zones
from cogs.worldclock_cog.config import DEFAULT_CLOCKS, MAX_CLOCKS, ZONE_ALIASES
from cogs.worldclock_cog.main import WorldClock
from cogs.worldclock_cog.views import ClockMenuLauncherView, ClockMenuView
from db.world_clock import SaveClockResult, SavedClock

SUMMER = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
WINTER = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("typed", "key"),
    [
        ("Berlin", "Europe/Berlin"),
        ("bogota", "America/Bogota"),
        ("Bogotá", "America/Bogota"),
        ("new york", "America/New_York"),
        ("Buenos Aires", "America/Argentina/Buenos_Aires"),
        ("CDMX", "America/Mexico_City"),
        ("europe/madrid", "Europe/Madrid"),
        ("UTC+2", "UTC+02:00"),
        ("gmt-5", "UTC-05:00"),
        ("+5:30", "UTC+05:30"),
        ("UTC−3", "UTC-03:00"),
        ("utc", "UTC+00:00"),
    ],
)
def test_resolve_zone(typed: str, key: str) -> None:
    assert zones.resolve_zone(typed) == key


@pytest.mark.parametrize("typed", ["", "Atlantis", "UTC+15", "UTC+5:20", "UTC-13"])
def test_resolve_zone_rejects(typed: str) -> None:
    assert zones.resolve_zone(typed) is None


def test_fixed_offset_sign_is_not_inverted() -> None:
    # Etc/GMT-2 means UTC+2; our fixed keys must not inherit that trap.
    zone = zones.zone_from_key(zones.resolve_zone("UTC+2") or "")
    assert SUMMER.astimezone(zone).hour == 14


def test_place_follows_daylight_saving() -> None:
    zone = zones.zone_from_key("Europe/Berlin")
    assert SUMMER.astimezone(zone).hour == 14
    assert WINTER.astimezone(zone).hour == 13


def test_defaults_and_aliases_are_canonical_zones() -> None:
    canonical = zones.canonical_zones()
    assert {key for _, key in DEFAULT_CLOCKS} <= canonical
    assert set(ZONE_ALIASES.values()) <= canonical


@pytest.mark.parametrize(
    ("typed", "key"),
    [("Calcutta", "Asia/Kolkata"), ("Kiev", "Europe/Kyiv"), ("Asia/Calcutta", "Asia/Calcutta")],
)
def test_old_city_names_map_to_canonical_zones(typed: str, key: str) -> None:
    # A legacy link name stays as-is only when typed as a full IANA name.
    assert zones.resolve_zone(typed) == key



def test_unknown_stored_zone_is_skipped() -> None:
    clocks = board.saved_clocks([SavedClock("Gone", "Nowhere/Town"), SavedClock("Ok", "Asia/Tokyo")])
    assert [c.label for c in clocks] == ["Ok"]


def test_cards_show_day_rollover_and_half_hour_difference() -> None:
    late = datetime(2026, 11, 14, 22, 0, tzinfo=UTC)
    clocks = [
        board.Clock("Delhi", zones.zone_from_key("Asia/Kolkata")),
        board.Clock("LA", zones.zone_from_key("America/Los_Angeles")),
    ]
    cards = board.build_cards(clocks, late, zones.home_zone(1))
    by_label = {c.label: c for c in cards}
    assert [c.label for c in cards] == ["LA", "You", "Delhi"]  # west to east
    assert by_label["Delhi"].day_shift == 1
    assert by_label["Delhi"].difference == "+4:30"
    assert by_label["LA"].difference == "−9h"
    assert by_label["You"].difference is None


def test_no_home_zone_means_no_you_card() -> None:
    cards = board.build_cards(board.default_clocks(), SUMMER, None)
    assert all(not c.is_you and c.difference is None for c in cards)
    assert len(cards) == len(board.default_clocks())


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("20:00", time(20)), ("20", time(20)), ("8pm", time(20)), ("8:30 am", time(8, 30)),
     ("12am", time(0)), ("12pm", time(12))],
)
def test_parse_clock_time(typed: str, expected: time) -> None:
    assert zones.parse_clock_time(typed) == expected


@pytest.mark.parametrize("typed", ["24:00", "13pm", "0am", "8:61", "soon"])
def test_parse_clock_time_rejects(typed: str) -> None:
    assert zones.parse_clock_time(typed) is None


def test_planned_instant_uses_home_zone() -> None:
    instant = board.planned_instant(time(20), zones.home_zone(-5), SUMMER)
    assert instant.astimezone(UTC) == datetime(2026, 7, 2, 1, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("label", "ok"),
    [("Emily", True), ("  Tía   Rosa ", True), ("小明", True), ("you", False),
     ("", False), ("x" * 17, False), ("Emily 🎉", False)],
)
def test_clean_label(label: str, ok: bool) -> None:
    assert (actions.clean_label(label) is not None) is ok


@pytest.mark.parametrize("count", range(1, 14))
def test_grid_shape_never_leaves_a_lone_card(count: int) -> None:
    columns, rows = renderer.grid_shape(count)
    last_row = count - columns * (rows - 1)
    assert rows <= 3
    assert 1 <= last_row <= columns
    assert count == 1 or last_row >= 2


def test_render_size_matches_grid() -> None:
    cards = board.build_cards(board.default_clocks()[:3], SUMMER, None)
    img = Image.open(renderer.render_world_clock(cards, "World clock", "now"))
    assert img.format == "PNG"
    assert img.width < img.height * 4  # one row of three, not a 4-wide grid


@dataclass
class FakeDB:
    """In-memory stand-in for the world clock and clock-pref queries."""

    clocks: list[SavedClock] = field(default_factory=list)
    offset: int | None = None

    async def get_world_clocks(self, user_id: int) -> list[SavedClock]:
        return list(self.clocks)

    async def get_user_clock_tz(self, user_id: int) -> int | None:
        return self.offset

    async def add_world_clock(self, user_id: int, label: str, zone: str, limit: int) -> SaveClockResult:
        for i, c in enumerate(self.clocks):
            if c.label.lower() == label.lower():
                self.clocks[i] = SavedClock(label, zone)
                return SaveClockResult.REPLACED
        if len(self.clocks) >= limit:
            return SaveClockResult.LIMIT_REACHED
        self.clocks.append(SavedClock(label, zone))
        return SaveClockResult.ADDED

    async def remove_world_clock(self, user_id: int, label: str) -> bool:
        before = len(self.clocks)
        self.clocks = [c for c in self.clocks if c.label.lower() != label.lower()]
        return len(self.clocks) < before

    async def clear_world_clocks(self, user_id: int) -> int:
        removed, self.clocks = len(self.clocks), []
        return removed


async def test_add_clock_stores_resolved_zone() -> None:
    db = FakeDB()
    outcome = await actions.add_clock(db, 1, "Emily", "Berlin")  # type: ignore[arg-type]
    assert outcome.ok
    assert db.clocks == [SavedClock("Emily", "Europe/Berlin")]


async def test_add_clock_reports_unknown_zone_without_saving() -> None:
    db = FakeDB()
    outcome = await actions.add_clock(db, 1, "Emily", "Atlantis")  # type: ignore[arg-type]
    assert not outcome.ok
    assert db.clocks == []


async def test_add_clock_at_limit_still_replaces_existing() -> None:
    db = FakeDB([SavedClock(f"c{i}", "Europe/Madrid") for i in range(MAX_CLOCKS)])
    full = await actions.add_clock(db, 1, "new", "Tokyo")  # type: ignore[arg-type]
    replaced = await actions.add_clock(db, 1, "C0", "Tokyo")  # type: ignore[arg-type]
    assert not full.ok
    assert replaced.ok
    assert db.clocks[0] == SavedClock("C0", "Asia/Tokyo")


async def test_board_falls_back_to_defaults_and_hints() -> None:
    rendered = await actions.render_board(FakeDB(), 1, None, now=SUMMER)  # type: ignore[arg-type]
    assert rendered.title == "🌍 World clock"
    assert "default cities" in rendered.body
    assert "$myclock" in rendered.body


async def test_planned_board_mentions_time() -> None:
    db = FakeDB([SavedClock("Emily", "Europe/Berlin")], offset=-5)
    rendered = await actions.render_board(db, 1, time(20), now=SUMMER)  # type: ignore[arg-type]
    assert rendered.title == "🌍 Your clocks"
    expected = int((datetime(2026, 7, 2, 1, tzinfo=UTC)).timestamp())
    assert f"<t:{expected}:F>" in rendered.body


@dataclass
class FakeResponse:
    """Records interaction responses."""

    sent: list[dict[str, Any]] = field(default_factory=list)
    edited: list[discord.ui.LayoutView] = field(default_factory=list)

    async def send_message(self, *args: Any, **kwargs: Any) -> None:
        self.sent.append(kwargs)

    async def edit_message(self, *, view: discord.ui.LayoutView) -> None:
        self.edited.append(view)


@dataclass
class FakeMessage:
    deleted: bool = False
    id: int = 99

    async def delete(self) -> None:
        self.deleted = True


@dataclass
class FakeInteraction:
    user: Any
    response: FakeResponse = field(default_factory=FakeResponse)
    message: FakeMessage = field(default_factory=FakeMessage)


@dataclass
class FakeContext:
    author: Any
    interaction: Any = None
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


def _bot(db: FakeDB) -> Any:
    return SimpleNamespace(db=db)


def _button(view: discord.ui.LayoutView, label: str) -> discord.ui.Button:
    return next(
        c for c in view.walk_children() if isinstance(c, discord.ui.Button) and c.label == label
    )


async def test_prefix_menu_posts_launcher_not_the_menu() -> None:
    cog = WorldClock.__new__(WorldClock)
    cog.bot = _bot(FakeDB([SavedClock("Emily", "Europe/Berlin")]))
    ctx = FakeContext(author=discord.Object(id=42))
    await cast(Any, cog.clock_menu.callback)(cog, ctx)
    [message] = ctx.sent
    view = message["view"]
    assert isinstance(view, ClockMenuLauncherView)
    assert view.is_persistent() and view.owner_id == 42
    assert "Emily" not in str(view.to_components())


async def test_slash_menu_replies_ephemerally() -> None:
    cog = WorldClock.__new__(WorldClock)
    cog.bot = _bot(FakeDB([SavedClock("Emily", "Europe/Berlin")]))
    interaction = FakeInteraction(user=discord.Object(id=42))
    ctx = FakeContext(author=interaction.user, interaction=interaction)
    await cast(Any, cog.clock_menu.callback)(cog, ctx)
    assert ctx.sent == []
    [reply] = interaction.response.sent
    assert reply["ephemeral"] is True
    assert isinstance(reply["view"], ClockMenuView)


@pytest.mark.parametrize(("clicker", "deleted"), [(42, True), (7, False)])
async def test_launcher_deletes_itself_only_for_its_owner(clicker: int, deleted: bool) -> None:
    launcher = ClockMenuLauncherView(_bot(FakeDB()), owner_id=42)
    interaction = FakeInteraction(user=discord.Object(id=clicker))
    await launcher.launch(cast(Any, interaction))
    assert interaction.response.sent[0]["ephemeral"] is True
    assert interaction.message.deleted is deleted


async def test_reset_waits_for_confirmation() -> None:
    db = FakeDB([SavedClock("Emily", "Europe/Berlin")])
    menu = ClockMenuView(_bot(db), 42, db.clocks)
    interaction = FakeInteraction(user=discord.Object(id=42))
    await _button(menu, "Reset all").callback(cast(Any, interaction))
    assert db.clocks  # nothing deleted yet
    confirm = interaction.response.edited[-1]
    await _button(confirm, "Yes, delete all").callback(cast(Any, interaction))
    assert db.clocks == []
