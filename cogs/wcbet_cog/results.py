"""ESPN results polling — pure parsing and matching helpers.

Free, key-less source: ESPN's unofficial scoreboard endpoint. Events are
matched to our fixtures by exact (kickoff UTC, home, away) after
normalizing the handful of team-name spelling differences, so a wrong or
rescheduled match can never settle the wrong bets — it simply won't
match and the owner falls back to `$wcbetadmin result`.

Kept free of Discord/DB/network so it can be exercised in isolation;
fetching and announcing live in `main.py`.
"""
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict

from cogs.wcpredict_cog.fixtures import (
    FIXTURES,
    Fixture,
    is_fixture_resolved,
    is_placeholder_team,
)

from .betting import Outcome, kickoff_utc

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/"
    "scoreboard?dates={date}"
)

# 30h covers overnight bot restarts and any reasonable ESPN reporting delay.
RESULT_WINDOW = timedelta(hours=30)

# ESPN displayName -> our fixtures.py name. Verified against all 72
# group-stage events: these five are the only differences.
TEAM_NAME_ALIASES: dict[str, str] = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Cape Verde": "Cabo Verde",
    "Congo DR": "DR Congo",
    "Ivory Coast": "Côte d'Ivoire",
    "United States": "USA",
}


class MatchResult(TypedDict):
    """A finished match mapped back to our fixture numbering.

    ``winner`` is the side ESPN flags as advancing ("home"/"away"), set
    even when the regulation/ET ``score`` is level (penalty shootout).
    ``None`` when ESPN exposes no winner (e.g. an ordinary group draw).
    """

    match_id: int
    home_score: int
    away_score: int
    winner: Outcome | None


def fixtures_awaiting_result(now_utc: datetime, settled_ids: set[int]) -> list[Fixture]:
    """Resolved fixtures that have kicked off, are unsettled, and are
    still within the polling window.

    Covers group-stage rows (always resolved) plus knockout rows whose
    teams have been filled in via `$wcbetadmin setteam`; unresolved
    knockout placeholders are skipped (no ESPN event to match yet).
    """
    awaiting: list[Fixture] = []
    for fixture in FIXTURES:
        if fixture["match_id"] in settled_ids:
            continue
        if not is_fixture_resolved(fixture):
            continue
        try:
            kickoff = kickoff_utc(fixture)
        except ValueError:
            continue
        if kickoff <= now_utc <= kickoff + RESULT_WINDOW:
            awaiting.append(fixture)
    return awaiting


def _normalize(name: str) -> str:
    return TEAM_NAME_ALIASES.get(name, name)


def _parse_event(
    event: dict,
) -> tuple[datetime, str, str, int, int, Outcome | None] | None:
    """Extract (kickoff_utc, home, away, home_score, away_score, winner) from
    one completed ESPN event, or None if it is unfinished or malformed.

    ``winner`` is "home"/"away" when ESPN flags an advancing side (set even
    on a level regulation score decided by penalties), else None.
    """
    try:
        competition = event["competitions"][0]
        if not competition["status"]["type"]["completed"]:
            return None
        kickoff = datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        teams: dict[str, tuple[str, int]] = {}
        winner: Outcome | None = None
        for competitor in competition["competitors"]:
            side = competitor["homeAway"]
            teams[side] = (
                _normalize(competitor["team"]["displayName"]),
                int(competitor["score"]),
            )
            if competitor.get("winner") is True and side in ("home", "away"):
                winner = side
        (home, home_score), (away, away_score) = teams["home"], teams["away"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return kickoff, home, away, home_score, away_score, winner


def _fixture_index(fixtures: list[Fixture]) -> dict[tuple[str, str], int]:
    """Index fixtures by the (home, away) identity ESPN events match on.

    Keyed on team names rather than kickoff time: ``fixtures`` is already
    the result-window set, where (home, away) is unique, so we don't need
    the kickoff in the key — and matching on it broke settlement when a
    match started late (ESPN's kickoff drifted from our stored time; e.g.
    a Round-of-32 tie that kicked off an hour late never settled).
    """
    return {(f["home"], f["away"]): f["match_id"] for f in fixtures}


def match_results(payload: dict, awaiting: list[Fixture]) -> list[MatchResult]:
    """Map completed events in an ESPN scoreboard payload onto the
    fixtures we are waiting on. Unmatched/unfinished events are ignored.

    Matching is by (home, away) team identity, not kickoff time, so a
    match that starts late (ESPN kickoff ≠ our stored time) still settles.
    """
    index = _fixture_index(awaiting)

    results: list[MatchResult] = []
    events = payload.get("events")
    if not isinstance(events, list):
        return results
    for event in events:
        parsed = _parse_event(event)
        if parsed is None:
            continue
        _kickoff, home, away, home_score, away_score, winner = parsed
        match_id = index.get((home, away))
        if match_id is not None:
            results.append(
                MatchResult(
                    match_id=match_id,
                    home_score=home_score,
                    away_score=away_score,
                    winner=winner,
                )
            )
    return results


# ── Knockout bracket resolution (teams from scheduled ESPN events) ──────────
class KnockoutResolution(TypedDict):
    """A knockout fixture whose real teams ESPN has now assigned."""

    match_id: int
    home: str
    away: str


def _parse_event_teams(event: dict) -> tuple[datetime, str | None, str | None] | None:
    """Extract (kickoff_utc, home, away) from any ESPN event, finished or not.

    Unlike ``_parse_event`` this does not require completion — it reads the
    competitor names so the bracket can be resolved before kickoff. A side
    is returned as None when ESPN still shows its own placeholder there
    ("Group L Winner", "Third Place Group …"); team names are alias-
    normalized to our spelling. Returns None on a malformed event.
    """
    try:
        competition = event["competitions"][0]
        kickoff = datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        sides: dict[str, str] = {}
        for competitor in competition["competitors"]:
            sides[competitor["homeAway"]] = _normalize(competitor["team"]["displayName"])
        home = sides.get("home")
        away = sides.get("away")
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    # An ESPN placeholder (not one of our 48 real teams) means "undecided".
    home = None if home is None or is_placeholder_team(home) else home
    away = None if away is None or is_placeholder_team(away) else away
    return kickoff, home, away


def knockout_resolutions(
    payload: dict, unresolved: list[Fixture],
) -> list[KnockoutResolution]:
    """Match scheduled ESPN events onto unresolved knockout fixtures by kickoff.

    For each fixture in ``unresolved`` whose kickoff matches an ESPN event,
    returns a resolution only when ESPN gives **both** real (non-placeholder)
    team names — a half-decided tie (one real team, one placeholder) is left
    for a later poll. ``unresolved`` should be the knockout fixtures that are
    not yet fully resolved; the kickoff index uses each fixture's shipped
    time, which is stable regardless of which teams fill the slot.
    """
    by_kickoff: dict[datetime, tuple[str | None, str | None]] = {}
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    for event in events:
        parsed = _parse_event_teams(event)
        if parsed is None:
            continue
        kickoff, home, away = parsed
        by_kickoff[kickoff] = (home, away)

    out: list[KnockoutResolution] = []
    for fixture in unresolved:
        try:
            kickoff = kickoff_utc(fixture)
        except ValueError:
            continue
        teams = by_kickoff.get(kickoff)
        if teams is None:
            continue
        home, away = teams
        if home is None or away is None:
            continue
        out.append(
            KnockoutResolution(match_id=fixture["match_id"], home=home, away=away)
        )
    return out


# ── Odds (DraftKings via the same scoreboard payload) ─────────────────────────

class MatchOdds(TypedDict):
    """Decimal 1X2 odds for one match."""

    home: Decimal
    draw: Decimal
    away: Decimal


class WcBet(TypedDict):
    """A row from ``wc_bets`` as returned by the bet query helpers.

    Models the ``asyncpg.Record`` shape these queries return so callers can
    index fields (``bet["stake"]``) with a known type. Rows are read-only
    at the call sites that use this alias.
    """

    user_id: int
    match_id: int
    guild_id: int
    outcome: str
    stake: int
    odds: Decimal
    status: str
    payout: int | None
    placed_at: object
    settled_at: object


class WcWallet(TypedDict):
    """A row from ``wc_bet_wallets`` (balance + bookkeeping columns)."""

    user_id: int
    guild_id: int
    balance: int
    last_allowance_date: object
    created_at: object
    updated_at: object


def apply_odds_multiplier(odds: MatchOdds, multiplier: Decimal) -> MatchOdds:
    """Scale all three legs by `multiplier`, quantized to 2dp (half-up).

    Used to juice the offered lines above ESPN's published prices. Pure
    Decimal math; the boosted price is what gets displayed, snapshotted,
    and paid, so the existing snapshot/drift invariants hold unchanged.
    A multiplier of 1 is the identity.
    """
    def scale(value: Decimal) -> Decimal:
        return (value * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return MatchOdds(
        home=scale(odds["home"]),
        draw=scale(odds["draw"]),
        away=scale(odds["away"]),
    )


def american_to_decimal(moneyline: int) -> Decimal:
    """Convert American moneyline odds to decimal odds (2dp, half-up).

    -235 → 1.43, +340 → 4.40, +750 → 8.50, ±100 → 2.00.
    """
    if moneyline == 0:
        raise ValueError("moneyline cannot be 0")
    if moneyline < 0:
        decimal_odds = 1 + Decimal(100) / Decimal(-moneyline)
    else:
        decimal_odds = 1 + Decimal(moneyline) / Decimal(100)
    return decimal_odds.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _moneyline(leg: dict) -> int:
    """Extract a side's moneyline from `close` (falling back to `open`)."""
    for key in ("close", "open"):
        node = leg.get(key)
        if isinstance(node, dict) and "odds" in node:
            return int(str(node["odds"]).replace("+", ""))
    raise KeyError("no close/open odds")


def parse_event_odds(event: dict) -> MatchOdds | None:
    """Extract decimal 1X2 odds from one ESPN event, or None.

    All-or-nothing: a missing or malformed leg disqualifies the whole
    match (mixed real/fallback prices would misprice the missing leg).
    """
    try:
        odds = event["competitions"][0]["odds"][0]
        moneyline = odds["moneyline"]
        home_ml = _moneyline(moneyline["home"])
        away_ml = _moneyline(moneyline["away"])
        draw_ml = int(odds["drawOdds"]["moneyLine"])
        return MatchOdds(
            home=american_to_decimal(home_ml),
            draw=american_to_decimal(draw_ml),
            away=american_to_decimal(away_ml),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _event_key(event: dict) -> tuple[str, str] | None:
    """The (home, away) team identity of an event, or None.

    Team-name identity (not kickoff) so odds still match when a match's
    scheduled time drifts — mirrors ``_fixture_index``.
    """
    try:
        teams: dict[str, str] = {}
        for competitor in event["competitions"][0]["competitors"]:
            teams[competitor["homeAway"]] = _normalize(competitor["team"]["displayName"])
        return teams["home"], teams["away"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def match_odds(payload: dict, fixtures: list[Fixture]) -> dict[int, MatchOdds]:
    """Map ESPN events to per-match decimal odds for the given fixtures.

    Matches without (complete) odds are simply absent — callers fall
    back to the flat default.
    """
    index = _fixture_index(fixtures)
    out: dict[int, MatchOdds] = {}
    events = payload.get("events")
    if not isinstance(events, list):
        return out
    for event in events:
        key = _event_key(event)
        if key is None:
            continue
        match_id = index.get(key)
        if match_id is None:
            continue
        odds = parse_event_odds(event)
        if odds is not None:
            out[match_id] = odds
    return out
