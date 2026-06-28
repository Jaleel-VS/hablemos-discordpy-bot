"""Tests for the pure ESPN results + odds helpers (`cogs.wcbet_cog.results`)."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cogs.wcbet_cog.betting import kickoff_utc
from cogs.wcbet_cog.results import (
    RESULT_WINDOW,
    MatchOdds,
    american_to_decimal,
    apply_odds_multiplier,
    fixtures_awaiting_result,
    knockout_resolutions,
    match_odds,
    match_results,
    parse_event_odds,
)
from cogs.wcpredict_cog.fixtures import FIXTURE_BY_ID

# Match 2: South Korea vs Czechia — kickoff 2026-06-12T02:00Z.
MATCH_2 = FIXTURE_BY_ID[2]
MATCH_2_KICKOFF = kickoff_utc(MATCH_2)

# Match 12: Bosnia and Herzegovina vs Qatar — exercises the alias map.
MATCH_12 = FIXTURE_BY_ID[12]


def _espn_event(
    fixture,
    home_score: int,
    away_score: int,
    *,
    completed: bool = True,
    home_name: str | None = None,
    away_name: str | None = None,
    winner: str | None = None,
) -> dict:
    """Minimal ESPN scoreboard event for a fixture.

    ``winner`` ("home"/"away") sets ESPN's per-competitor ``winner`` flag,
    used for knockout shootouts where the score is level.
    """
    return {
        "date": kickoff_utc(fixture).strftime("%Y-%m-%dT%H:%MZ"),
        "competitions": [
            {
                "status": {"type": {"completed": completed}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": str(home_score),
                        "winner": winner == "home",
                        "team": {"displayName": home_name or fixture["home"]},
                    },
                    {
                        "homeAway": "away",
                        "score": str(away_score),
                        "winner": winner == "away",
                        "team": {"displayName": away_name or fixture["away"]},
                    },
                ],
            }
        ],
    }


# ── fixtures_awaiting_result ──────────────────────────────────────────────────

def test_awaiting_excludes_not_yet_kicked_off() -> None:
    before = MATCH_2_KICKOFF - timedelta(minutes=1)
    ids = {f["match_id"] for f in fixtures_awaiting_result(before, set())}
    assert 2 not in ids


def test_awaiting_includes_match_in_window() -> None:
    during = MATCH_2_KICKOFF + timedelta(hours=2)
    ids = {f["match_id"] for f in fixtures_awaiting_result(during, set())}
    assert 2 in ids


def test_awaiting_excludes_settled() -> None:
    during = MATCH_2_KICKOFF + timedelta(hours=2)
    ids = {f["match_id"] for f in fixtures_awaiting_result(during, {2})}
    assert 2 not in ids


def test_awaiting_excludes_beyond_window() -> None:
    long_after = MATCH_2_KICKOFF + RESULT_WINDOW + timedelta(minutes=1)
    ids = {f["match_id"] for f in fixtures_awaiting_result(long_after, set())}
    assert 2 not in ids


# ── match_results ─────────────────────────────────────────────────────────────

def test_completed_event_maps_to_match_id() -> None:
    payload = {"events": [_espn_event(MATCH_2, 2, 1)]}
    assert match_results(payload, [MATCH_2]) == [
        {"match_id": 2, "home_score": 2, "away_score": 1, "winner": None}
    ]


def test_unfinished_event_is_ignored() -> None:
    payload = {"events": [_espn_event(MATCH_2, 1, 0, completed=False)]}
    assert match_results(payload, [MATCH_2]) == []


def test_espn_team_name_aliases_are_normalized() -> None:
    payload = {"events": [_espn_event(MATCH_12, 0, 0, home_name="Bosnia-Herzegovina")]}
    assert match_results(payload, [MATCH_12]) == [
        {"match_id": 12, "home_score": 0, "away_score": 0, "winner": None}
    ]


def test_winner_flag_is_captured() -> None:
    # A 1-1 knockout decided on penalties: score level, ESPN flags a winner.
    payload = {"events": [_espn_event(MATCH_2, 1, 1, winner="home")]}
    assert match_results(payload, [MATCH_2]) == [
        {"match_id": 2, "home_score": 1, "away_score": 1, "winner": "home"}
    ]


def test_winner_flag_away() -> None:
    payload = {"events": [_espn_event(MATCH_2, 0, 0, winner="away")]}
    assert match_results(payload, [MATCH_2])[0]["winner"] == "away"


def test_no_winner_flag_leaves_winner_none() -> None:
    payload = {"events": [_espn_event(MATCH_2, 3, 1)]}
    assert match_results(payload, [MATCH_2])[0]["winner"] is None


def test_event_not_in_awaiting_list_is_ignored() -> None:
    payload = {"events": [_espn_event(MATCH_2, 2, 1)]}
    assert match_results(payload, [MATCH_12]) == []


def test_kickoff_mismatch_does_not_match() -> None:
    event = _espn_event(MATCH_2, 2, 1)
    event["date"] = (MATCH_2_KICKOFF + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
    assert match_results({"events": [event]}, [MATCH_2]) == []


# ── malformed payload safety (parsers never crash) ───────────────────────────

def test_missing_events_key() -> None:
    assert match_results({}, [MATCH_2]) == []


def test_events_not_a_list() -> None:
    assert match_results({"events": "nope"}, [MATCH_2]) == []


def test_malformed_event_is_skipped() -> None:
    good = _espn_event(MATCH_2, 2, 1)
    bad_score = _espn_event(MATCH_2, 0, 0)
    bad_score["competitions"][0]["competitors"][0]["score"] = "abc"
    bad_date = _espn_event(MATCH_2, 0, 0)
    bad_date["date"] = "tomorrow-ish"
    payload = {"events": [{}, {"competitions": []}, bad_score, bad_date, good]}
    assert match_results(payload, [MATCH_2]) == [
        {"match_id": 2, "home_score": 2, "away_score": 1, "winner": None}
    ]


def test_missing_home_or_away_competitor_is_skipped() -> None:
    event = _espn_event(MATCH_2, 2, 1)
    event["competitions"][0]["competitors"] = event["competitions"][0]["competitors"][:1]
    assert match_results({"events": [event]}, [MATCH_2]) == []


def test_real_window_now_is_naive_safe() -> None:
    # Guard: callers must pass aware datetimes; an aware now works end-to-end.
    now = datetime(2026, 6, 12, 3, 0, tzinfo=UTC)
    ids = {f["match_id"] for f in fixtures_awaiting_result(now, set())}
    assert 2 in ids  # 02:00Z kickoff + 1h


# ── odds parsing ─────────────────────────────────────────────────────────────

def _odds_block(
    home_ml: str = "-235",
    away_ml: str = "+750",
    draw_ml: int = 340,
) -> dict:
    """Minimal ESPN odds object as found in competitions[0]['odds'][0]."""
    return {
        "provider": {"name": "DraftKings"},
        "moneyline": {
            "home": {"close": {"odds": home_ml}},
            "away": {"close": {"odds": away_ml}},
        },
        "drawOdds": {"moneyLine": draw_ml},
    }


def _event_with_odds(fixture, odds_block: dict | None) -> dict:
    event = _espn_event(fixture, 0, 0, completed=False)
    if odds_block is not None:
        event["competitions"][0]["odds"] = [odds_block]
    return event


@pytest.mark.parametrize(
    ("moneyline", "expected"),
    [
        (-235, Decimal("1.43")),
        (340, Decimal("4.40")),
        (750, Decimal("8.50")),
        (-100, Decimal("2.00")),
        (100, Decimal("2.00")),
        (-110, Decimal("1.91")),  # 1.909… rounds half-up
    ],
)
def test_american_to_decimal(moneyline: int, expected: Decimal) -> None:
    assert american_to_decimal(moneyline) == expected


def test_american_to_decimal_rejects_zero() -> None:
    with pytest.raises(ValueError):
        american_to_decimal(0)


def test_parse_event_odds_full_line() -> None:
    event = _event_with_odds(MATCH_2, _odds_block())
    assert parse_event_odds(event) == MatchOdds(
        home=Decimal("1.43"), draw=Decimal("4.40"), away=Decimal("8.50"),
    )


def test_parse_event_odds_falls_back_to_open() -> None:
    block = _odds_block()
    block["moneyline"]["home"] = {"open": {"odds": "-170"}}
    odds = parse_event_odds(_event_with_odds(MATCH_2, block))
    assert odds is not None and odds["home"] == Decimal("1.59")


@pytest.mark.parametrize("missing", ["home", "away"])
def test_parse_event_odds_missing_moneyline_leg(missing: str) -> None:
    block = _odds_block()
    del block["moneyline"][missing]
    assert parse_event_odds(_event_with_odds(MATCH_2, block)) is None


def test_parse_event_odds_missing_draw_leg() -> None:
    block = _odds_block()
    del block["drawOdds"]
    assert parse_event_odds(_event_with_odds(MATCH_2, block)) is None


def test_parse_event_odds_no_odds_at_all() -> None:
    assert parse_event_odds(_event_with_odds(MATCH_2, None)) is None


def test_parse_event_odds_garbage_moneyline() -> None:
    block = _odds_block(home_ml="soon™")
    assert parse_event_odds(_event_with_odds(MATCH_2, block)) is None


def test_match_odds_maps_to_match_id() -> None:
    payload = {"events": [_event_with_odds(MATCH_2, _odds_block())]}
    odds = match_odds(payload, [MATCH_2])
    assert odds == {2: MatchOdds(
        home=Decimal("1.43"), draw=Decimal("4.40"), away=Decimal("8.50"),
    )}


def test_match_odds_skips_unpriced_and_unmatched() -> None:
    payload = {"events": [
        _event_with_odds(MATCH_2, None),               # no line yet
        _event_with_odds(MATCH_12, _odds_block()),     # not in fixtures arg
    ]}
    assert match_odds(payload, [MATCH_2]) == {}


# ── odds multiplier (house boost) ───────────────────────────────────────────

def test_apply_odds_multiplier_scales_all_legs() -> None:
    odds = MatchOdds(home=Decimal("1.43"), draw=Decimal("4.40"), away=Decimal("8.50"))
    boosted = apply_odds_multiplier(odds, Decimal("1.5"))
    assert boosted == MatchOdds(
        home=Decimal("2.15"), draw=Decimal("6.60"), away=Decimal("12.75"),
    )


def test_apply_odds_multiplier_identity() -> None:
    odds = MatchOdds(home=Decimal("1.43"), draw=Decimal("4.40"), away=Decimal("8.50"))
    assert apply_odds_multiplier(odds, Decimal("1")) == odds


def test_apply_odds_multiplier_rounds_half_up() -> None:
    # 1.43 * 1.05 = 1.5015 -> 1.50 (rounds down); 4.40 * 1.05 = 4.62 exact.
    odds = MatchOdds(home=Decimal("1.43"), draw=Decimal("4.40"), away=Decimal("2.005"))
    boosted = apply_odds_multiplier(odds, Decimal("1.05"))
    assert boosted["home"] == Decimal("1.50")
    assert boosted["draw"] == Decimal("4.62")
    # 2.005 * 1.05 = 2.10525 -> 2.11
    assert boosted["away"] == Decimal("2.11")


# ── knockout_resolutions ─────────────────────────────────────────────
# Match 73: Round of 32, ships as "Runner-up Group A" vs "Runner-up Group B".
MATCH_73 = FIXTURE_BY_ID[73]


def _scheduled_event(fixture, home_name: str, away_name: str) -> dict:
    """A not-yet-played ESPN event with the given competitor display names."""
    return {
        "date": kickoff_utc(fixture).strftime("%Y-%m-%dT%H:%MZ"),
        "competitions": [
            {
                "status": {"type": {"completed": False}},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": home_name}},
                    {"homeAway": "away", "team": {"displayName": away_name}},
                ],
            }
        ],
    }


def test_knockout_resolution_both_teams_real() -> None:
    payload = {"events": [_scheduled_event(MATCH_73, "Mexico", "Brazil")]}
    res = knockout_resolutions(payload, [MATCH_73])
    assert res == [{"match_id": 73, "home": "Mexico", "away": "Brazil"}]


def test_knockout_resolution_normalizes_espn_aliases() -> None:
    # ESPN spells these differently; the alias map maps them to our names.
    payload = {"events": [_scheduled_event(MATCH_73, "Ivory Coast", "United States")]}
    res = knockout_resolutions(payload, [MATCH_73])
    assert res == [{"match_id": 73, "home": "Côte d'Ivoire", "away": "USA"}]


def test_knockout_resolution_skips_half_decided() -> None:
    # ESPN still shows its own placeholder for one side -> not resolvable yet.
    payload = {"events": [_scheduled_event(MATCH_73, "Mexico", "Group B Runner-up")]}
    assert knockout_resolutions(payload, [MATCH_73]) == []


def test_knockout_resolution_skips_both_placeholders() -> None:
    payload = {
        "events": [_scheduled_event(MATCH_73, "Group A Runner-up", "Group B Runner-up")]
    }
    assert knockout_resolutions(payload, [MATCH_73]) == []


def test_knockout_resolution_matches_by_kickoff_time() -> None:
    # An event at a different kickoff than the fixture must not match.
    other = _scheduled_event(FIXTURE_BY_ID[74], "Mexico", "Brazil")
    assert knockout_resolutions({"events": [other]}, [MATCH_73]) == []


def test_knockout_resolution_ignores_malformed_events() -> None:
    payload = {"events": [{}, {"competitions": []}, None]}
    assert knockout_resolutions(payload, [MATCH_73]) == []


def test_knockout_resolution_empty_payload() -> None:
    assert knockout_resolutions({}, [MATCH_73]) == []
    assert knockout_resolutions({"events": "nope"}, [MATCH_73]) == []
