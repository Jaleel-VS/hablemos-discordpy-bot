"""Tests for knockout fixture resolution — overrides + bettable gating.

Knockout fixtures ship with bracket placeholders ("Winner Group A") and
are excluded from betting/settlement until an owner resolves their real
teams via `$wcbetadmin setteam`. These tests cover the pure resolution
helpers in `cogs.wcpredict_cog.fixtures`, the broadened
`betting.bettable_fixtures`, and the `_parse_setteam` admin parser.

Resolution mutates shared module-level fixture dicts in place, so each
test that applies an override restores the original teams afterward.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cogs.wcbet_cog.admin import _parse_result_arg, _parse_setteam
from cogs.wcbet_cog.betting import bettable_fixtures, kickoff_utc
from cogs.wcpredict_cog.fixtures import (
    FIXTURE_BY_ID,
    apply_fixture_override,
    is_fixture_resolved,
    is_placeholder_team,
)

# Match 73: Round of 32, kicks off 2026-06-28 19:00 UTC, both sides
# placeholders ("Runner-up Group A" / "Runner-up Group B").
R32_MATCH_ID = 73


@pytest.fixture
def restore_match_73():
    """Snapshot and restore match 73's mutable team/time fields."""
    fixture = FIXTURE_BY_ID[R32_MATCH_ID]
    snapshot = {k: fixture[k] for k in ("home", "away", "time_et")}
    yield fixture
    fixture["home"] = snapshot["home"]
    fixture["away"] = snapshot["away"]
    fixture["time_et"] = snapshot["time_et"]


# ── placeholder / resolution predicates ──────────────────────────────────────


def test_real_team_is_not_placeholder() -> None:
    assert not is_placeholder_team("Mexico")
    assert not is_placeholder_team("Côte d'Ivoire")


def test_bracket_strings_are_placeholders() -> None:
    assert is_placeholder_team("Winner Group A")
    assert is_placeholder_team("Runner-up Group B")
    assert is_placeholder_team("Best 3rd (A/B/C/D/F)")
    assert is_placeholder_team("Winner Match 73")


def test_group_stage_fixture_is_resolved() -> None:
    assert is_fixture_resolved(FIXTURE_BY_ID[1])


def test_unresolved_knockout_is_not_resolved() -> None:
    assert not is_fixture_resolved(FIXTURE_BY_ID[R32_MATCH_ID])


# ── apply_fixture_override ────────────────────────────────────────────────────


def test_apply_override_resolves_teams(restore_match_73) -> None:
    apply_fixture_override(R32_MATCH_ID, "Mexico", "Brazil")
    fixture = FIXTURE_BY_ID[R32_MATCH_ID]
    assert fixture["home"] == "Mexico"
    assert fixture["away"] == "Brazil"
    assert is_fixture_resolved(fixture)


def test_apply_override_keeps_time_when_none(restore_match_73) -> None:
    original_time = FIXTURE_BY_ID[R32_MATCH_ID]["time_et"]
    apply_fixture_override(R32_MATCH_ID, "Mexico", "Brazil", None)
    assert FIXTURE_BY_ID[R32_MATCH_ID]["time_et"] == original_time


def test_apply_override_updates_time_when_given(restore_match_73) -> None:
    apply_fixture_override(R32_MATCH_ID, "Mexico", "Brazil", "16:00")
    assert FIXTURE_BY_ID[R32_MATCH_ID]["time_et"] == "16:00"


def test_apply_override_unknown_match_returns_none() -> None:
    assert apply_fixture_override(9999, "A", "B") is None


# ── bettable_fixtures gating ──────────────────────────────────────────────────


def _just_before(match_id: int) -> datetime:
    """An aware-UTC instant one hour before the fixture kicks off."""
    return kickoff_utc(FIXTURE_BY_ID[match_id]) - timedelta(hours=1)


def test_unresolved_knockout_not_bettable(restore_match_73) -> None:
    now = _just_before(R32_MATCH_ID)
    ids = {f["match_id"] for f in bettable_fixtures(now)}
    assert R32_MATCH_ID not in ids


def test_resolved_knockout_is_bettable(restore_match_73) -> None:
    apply_fixture_override(R32_MATCH_ID, "Mexico", "Brazil")
    now = _just_before(R32_MATCH_ID)
    ids = {f["match_id"] for f in bettable_fixtures(now)}
    assert R32_MATCH_ID in ids


def test_resolved_knockout_respects_48h_window(restore_match_73) -> None:
    apply_fixture_override(R32_MATCH_ID, "Mexico", "Brazil")
    # Three days before kickoff — outside the 48h lookahead.
    far = kickoff_utc(FIXTURE_BY_ID[R32_MATCH_ID]) - timedelta(hours=72)
    ids = {f["match_id"] for f in bettable_fixtures(far)}
    assert R32_MATCH_ID not in ids


def test_resolved_knockout_excluded_after_kickoff(restore_match_73) -> None:
    apply_fixture_override(R32_MATCH_ID, "Mexico", "Brazil")
    after = kickoff_utc(FIXTURE_BY_ID[R32_MATCH_ID]) + timedelta(minutes=1)
    ids = {f["match_id"] for f in bettable_fixtures(after)}
    assert R32_MATCH_ID not in ids


# ── _parse_setteam ────────────────────────────────────────────────────────────


def test_parse_setteam_basic() -> None:
    assert _parse_setteam("Mexico vs Brazil") == ("Mexico", "Brazil", None)


def test_parse_setteam_with_time() -> None:
    assert _parse_setteam("Spain vs France @ 16:00") == ("Spain", "France", "16:00")


def test_parse_setteam_normalizes_time_padding() -> None:
    assert _parse_setteam("A vs B @ 9:05") == ("A", "B", "09:05")


def test_parse_setteam_team_names_with_spaces_and_accents() -> None:
    assert _parse_setteam("Côte d'Ivoire vs South Korea") == (
        "Côte d'Ivoire",
        "South Korea",
        None,
    )


def test_parse_setteam_vs_is_word_boundary() -> None:
    # "Curaçao" contains no standalone "vs"; the separator must be the word.
    assert _parse_setteam("Curaçao vs Ecuador") == ("Curaçao", "Ecuador", None)


def test_parse_setteam_rejects_missing_separator() -> None:
    assert _parse_setteam("Mexico Brazil") is None


def test_parse_setteam_rejects_bad_time() -> None:
    assert _parse_setteam("A vs B @ 25:00") is None
    assert _parse_setteam("A vs B @ 12:99") is None


# ── _parse_result_arg (knockout shootout marker) ──────────────────────────────

def test_parse_result_arg_plain_score() -> None:
    assert _parse_result_arg("2-1") == ("2-1", None)


def test_parse_result_arg_pens_home() -> None:
    assert _parse_result_arg("1-1 pens home") == ("1-1", "home")


def test_parse_result_arg_pens_away() -> None:
    assert _parse_result_arg("0-0 pens away") == ("0-0", "away")


def test_parse_result_arg_accepts_penalties_and_colon() -> None:
    assert _parse_result_arg("2-2 penalties away") == ("2-2", "away")
    assert _parse_result_arg("1-1 pens: home") == ("1-1", "home")


def test_parse_result_arg_is_case_insensitive() -> None:
    assert _parse_result_arg("1-1 PENS Home") == ("1-1", "home")


def test_parse_result_arg_ignores_unrelated_trailing_text() -> None:
    # No recognised pens marker -> whole string is the score part.
    score, side = _parse_result_arg("2-1 nonsense")
    assert side is None
    assert score == "2-1 nonsense"
