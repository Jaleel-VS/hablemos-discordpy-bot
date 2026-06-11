"""Tests for the pure ESPN results helpers (`cogs.wcbet_cog.results`)."""
from datetime import UTC, datetime, timedelta

from cogs.wcbet_cog.betting import kickoff_utc
from cogs.wcbet_cog.results import (
    RESULT_WINDOW,
    fixtures_awaiting_result,
    match_results,
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
) -> dict:
    """Minimal ESPN scoreboard event for a fixture."""
    return {
        "date": kickoff_utc(fixture).strftime("%Y-%m-%dT%H:%MZ"),
        "competitions": [
            {
                "status": {"type": {"completed": completed}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": str(home_score),
                        "team": {"displayName": home_name or fixture["home"]},
                    },
                    {
                        "homeAway": "away",
                        "score": str(away_score),
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
        {"match_id": 2, "home_score": 2, "away_score": 1}
    ]


def test_unfinished_event_is_ignored() -> None:
    payload = {"events": [_espn_event(MATCH_2, 1, 0, completed=False)]}
    assert match_results(payload, [MATCH_2]) == []


def test_espn_team_name_aliases_are_normalized() -> None:
    payload = {"events": [_espn_event(MATCH_12, 0, 0, home_name="Bosnia-Herzegovina")]}
    assert match_results(payload, [MATCH_12]) == [
        {"match_id": 12, "home_score": 0, "away_score": 0}
    ]


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
        {"match_id": 2, "home_score": 2, "away_score": 1}
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
