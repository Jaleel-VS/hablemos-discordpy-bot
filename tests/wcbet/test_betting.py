"""Tests for cogs.wcbet_cog.betting — pure logic, no fakes needed.

All time-dependent functions take a frozen aware-UTC ``now_utc``;
fixtures referenced by ``match_id`` are the real 2026 rows from
`cogs.wcpredict_cog.fixtures` (verified against FIFA's schedule).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cogs.wcbet_cog.betting import (
    bettable_fixtures,
    combined_odds,
    current_streak,
    kickoff_utc,
    outcome_from_score,
    parlay_payout,
    parse_score,
    parse_stake,
    payout,
    stake_presets,
)
from cogs.wcpredict_cog.fixtures import FIXTURE_BY_ID, Fixture


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ── kickoff_utc ──────────────────────────────────────────────────────────────


def test_kickoff_utc_converts_et_to_utc() -> None:
    # Match 1: Mexico vs South Africa, 2026-06-11 15:00 ET → 19:00 UTC.
    assert kickoff_utc(FIXTURE_BY_ID[1]) == _utc(2026, 6, 11, 19)


def test_kickoff_utc_late_kickoff_crosses_utc_midnight() -> None:
    # Match 2: South Korea vs Czechia, 2026-06-11 22:00 ET → 02:00 UTC *next day*.
    assert kickoff_utc(FIXTURE_BY_ID[2]) == _utc(2026, 6, 12, 2)


def test_kickoff_utc_result_is_aware_utc() -> None:
    kickoff = kickoff_utc(FIXTURE_BY_ID[1])
    assert kickoff.tzinfo == UTC


def test_kickoff_utc_tbd_raises() -> None:
    tbd: Fixture = {
        "match_id": 999, "stage": "Round of 32", "group": None,
        "date": "2026-06-28", "time_et": "TBD",
        "home": "Winner Group A", "away": "Runner-up Group B",
        "venue": "n/a", "city": "n/a",
    }
    with pytest.raises(ValueError):
        kickoff_utc(tbd)


# ── bettable_fixtures ────────────────────────────────────────────────────────


def test_bettable_fixtures_invariants() -> None:
    now = _utc(2026, 6, 11, 12)  # 08:00 ET, before any June 11 kick-off
    fixtures = bettable_fixtures(now)
    assert fixtures, "June 11 has scheduled group-stage matches"
    for fixture in fixtures:
        assert fixture["group"] is not None
        assert kickoff_utc(fixture) > now
        assert kickoff_utc(fixture) <= now + timedelta(hours=24)


def test_bettable_fixtures_excludes_started_matches() -> None:
    # 20:00 UTC = 16:00 ET: match 1 (15:00 ET) kicked off, match 2 (22:00 ET) not.
    fixtures = bettable_fixtures(_utc(2026, 6, 11, 20))
    ids = {f["match_id"] for f in fixtures}
    assert 1 not in ids
    assert 2 in ids


def test_bettable_fixtures_excludes_far_future() -> None:
    # 12:00 UTC on June 10 — tournament hasn't started and June 11 is >24h away.
    ids = {f["match_id"] for f in bettable_fixtures(_utc(2026, 6, 10, 12))}
    assert 1 not in ids
    assert 2 not in ids


def test_bettable_fixtures_utc_midnight_is_still_et_evening() -> None:
    # 2026-06-12 01:00 UTC = 2026-06-11 21:00 ET: match 2 (22:00 ET) still bettable.
    fixtures = bettable_fixtures(_utc(2026, 6, 12, 1))
    ids = {f["match_id"] for f in fixtures}
    assert 2 in ids


def test_bettable_fixtures_late_et_evening_after_last_kickoff() -> None:
    # 2026-06-12 03:00 UTC = 2026-06-11 23:00 ET: every June 11 match has kicked off.
    # But June 12 matches (e.g. match 7 at 19:00 UTC) are within 24h, so they appear.
    ids = {f["match_id"] for f in bettable_fixtures(_utc(2026, 6, 12, 3))}
    assert 1 not in ids  # match 1 already kicked off
    assert 2 not in ids  # match 2 already kicked off
    assert 7 in ids      # match 7 kicks off in ~16h


def test_bettable_fixtures_midnight_et_kickoff_visible_day_before() -> None:
    # Match 20 kicks off at 04:00 UTC Jun 14 (00:00 ET).
    # At 05:00 UTC Jun 13 (01:00 ET Jun 13) it's within 24h — should be bettable.
    ids = {f["match_id"] for f in bettable_fixtures(_utc(2026, 6, 13, 5))}
    assert 20 in ids


def test_bettable_fixtures_et_midnight_rolls_to_next_day() -> None:
    # 2026-06-12 04:00 UTC = 2026-06-12 00:00 ET: June 11 rows are gone.
    for fixture in bettable_fixtures(_utc(2026, 6, 12, 4)):
        assert fixture["date"] == "2026-06-12"


# ── outcome_from_score ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("home", "away", "expected"),
    [
        (2, 1, "home"),
        (0, 3, "away"),
        (1, 1, "draw"),
        (0, 0, "draw"),
    ],
)
def test_outcome_from_score(home: int, away: int, expected: str) -> None:
    assert outcome_from_score(home, away) == expected


# ── payout ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("stake", "odds", "expected"),
    [
        (100, Decimal("1.5"), 150),
        (101, Decimal("1.5"), 151),   # floor(151.5)
        (1, Decimal("1.5"), 1),       # floor(1.5)
        (2, Decimal("1.5"), 3),
        (10_000, Decimal("1.5"), 15_000),
        (3, Decimal("4.40"), 13),     # floor(13.2)
        (500, Decimal("8.50"), 4_250),
        (7, Decimal("2.00"), 14),
    ],
)
def test_payout_floors(stake: int, odds: Decimal, expected: int) -> None:
    assert payout(stake, odds) == expected


def test_combined_odds_product() -> None:
    assert combined_odds([Decimal("1.43"), Decimal("2.15")]) == Decimal("3.07")
    assert combined_odds([Decimal("2.00"), Decimal("2.00"), Decimal("2.00")]) == Decimal("8.00")


def test_combined_odds_empty_is_identity() -> None:
    assert combined_odds([]) == Decimal("1.00")


def test_parlay_payout_floors() -> None:
    # 5000 * (1.43 * 2.15 = 3.0745 -> 3.07) = 15350
    assert parlay_payout(5_000, [Decimal("1.43"), Decimal("2.15")]) == 15_350


def test_parlay_payout_single_leg_matches_payout() -> None:
    # A 1-leg parlay must agree with a plain single bet.
    assert parlay_payout(500, [Decimal("1.50")]) == payout(500, Decimal("1.50"))


def test_current_streak_wins() -> None:
    assert current_streak(["won", "won", "lost", "won"]) == ("won", 2)


def test_current_streak_losses() -> None:
    assert current_streak(["lost", "lost", "lost", "won"]) == ("lost", 3)


def test_current_streak_empty() -> None:
    assert current_streak([]) is None


# ── stake_presets ────────────────────────────────────────────────────────────


def test_stake_presets_broke_user() -> None:
    assert stake_presets(0) == []


def test_stake_presets_small_balance_is_all_in_only() -> None:
    assert stake_presets(50) == [50]


def test_stake_presets_filters_and_appends_all_in() -> None:
    assert stake_presets(1_337) == [100, 250, 500, 1_000, 1_337]


def test_stake_presets_no_duplicate_when_balance_is_a_preset() -> None:
    assert stake_presets(500) == [100, 250, 500]


def test_stake_presets_full_spread() -> None:
    assert stake_presets(10_000) == [100, 250, 500, 1_000, 2_500, 5_000, 10_000]


# ── parse_score ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2-1", (2, 1)),
        ("2:1", (2, 1)),
        ("2 1", (2, 1)),
        (" 2 - 1 ", (2, 1)),
        ("0-0", (0, 0)),
        ("10-0", (10, 0)),
    ],
)
def test_parse_score_valid(raw: str, expected: tuple[int, int]) -> None:
    assert parse_score(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "garbage",
        "2",
        "2-",
        "-1",
        "2--1",   # negative away score
        "-2-1",   # negative home score
        "2/1",    # unsupported separator
        "2-1-3",
        "a-b",
        "2.5-1",
        "100-0",  # out of bounds (3 digits)
    ],
)
def test_parse_score_rejects(raw: str) -> None:
    assert parse_score(raw) is None


# ── parse_stake ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "balance", "expected"),
    [
        ("500", 1_000, 500),
        ("1", 1_000, 1),
        ("1000", 1_000, 1_000),
        ("  500  ", 1_000, 500),    # whitespace tolerated
        ("all", 1_000, 1_000),
        ("ALL", 1_000, 1_000),
        (" all ", 1_000, 1_000),
    ],
)
def test_parse_stake_valid(raw: str, balance: int, expected: int) -> None:
    assert parse_stake(raw, balance) == expected


@pytest.mark.parametrize(
    ("raw", "balance"),
    [
        ("abc", 1_000),     # non-numeric
        ("", 1_000),
        ("   ", 1_000),
        ("0", 1_000),       # zero
        ("-5", 1_000),      # negative
        ("1001", 1_000),    # over balance
        ("1.5", 1_000),     # not an int
        ("all", 0),         # "all" with empty wallet is still no bet
    ],
)
def test_parse_stake_rejects(raw: str, balance: int) -> None:
    assert parse_stake(raw, balance) is None
