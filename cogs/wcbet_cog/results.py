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
from typing import TypedDict

from cogs.wcpredict_cog.fixtures import GROUP_STAGE_FIXTURES, Fixture

from .betting import kickoff_utc

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/"
    "scoreboard?dates={date}"
)

# How long after kickoff we keep looking for a result before giving up
# (regulation + stoppage + generous slack; group stage has no extra time).
RESULT_WINDOW = timedelta(hours=6)

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
    """A finished match mapped back to our fixture numbering."""

    match_id: int
    home_score: int
    away_score: int


def fixtures_awaiting_result(now_utc: datetime, settled_ids: set[int]) -> list[Fixture]:
    """Group-stage fixtures that have kicked off, are unsettled, and are
    still within the polling window."""
    awaiting: list[Fixture] = []
    for fixture in GROUP_STAGE_FIXTURES:
        if fixture["match_id"] in settled_ids:
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


def _parse_event(event: dict) -> tuple[datetime, str, str, int, int] | None:
    """Extract (kickoff_utc, home, away, home_score, away_score) from one
    completed ESPN event, or None if it is unfinished or malformed."""
    try:
        competition = event["competitions"][0]
        if not competition["status"]["type"]["completed"]:
            return None
        kickoff = datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        teams: dict[str, tuple[str, int]] = {}
        for competitor in competition["competitors"]:
            teams[competitor["homeAway"]] = (
                _normalize(competitor["team"]["displayName"]),
                int(competitor["score"]),
            )
        (home, home_score), (away, away_score) = teams["home"], teams["away"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return kickoff, home, away, home_score, away_score


def match_results(payload: dict, awaiting: list[Fixture]) -> list[MatchResult]:
    """Map completed events in an ESPN scoreboard payload onto the
    fixtures we are waiting on. Unmatched/unfinished events are ignored."""
    index: dict[tuple[datetime, str, str], int] = {}
    for fixture in awaiting:
        index[(kickoff_utc(fixture), fixture["home"], fixture["away"])] = fixture["match_id"]

    results: list[MatchResult] = []
    events = payload.get("events")
    if not isinstance(events, list):
        return results
    for event in events:
        parsed = _parse_event(event)
        if parsed is None:
            continue
        kickoff, home, away, home_score, away_score = parsed
        match_id = index.get((kickoff, home, away))
        if match_id is not None:
            results.append(
                MatchResult(match_id=match_id, home_score=home_score, away_score=away_score)
            )
    return results
