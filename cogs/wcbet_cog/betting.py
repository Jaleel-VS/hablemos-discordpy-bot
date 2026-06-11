"""Pure betting logic for World Cup match betting.

Kept free of Discord/DB types so it can be exercised in isolation
(mirrors `cogs.wcpredict_cog.scoring`). All time-dependent functions
take an aware UTC ``now_utc`` parameter — never call ``datetime.now()``
here.

Kick-off times in `fixtures.py` are Eastern Time at a fixed UTC−4
offset (EDT holds for the entire June–July 2026 tournament window).
"""
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from cogs.wcpredict_cog.fixtures import GROUP_STAGE_FIXTURES, Fixture

type Outcome = Literal["home", "draw", "away"]

# Fixed Eastern Daylight Time offset for the tournament window.
ET_OFFSET = timezone(timedelta(hours=-4))

# "2-1", "2:1", "2 1" — non-negative scores, at most two digits each.
_SCORE_RE = re.compile(r"(\d{1,2})(?:\s*[-:]\s*|\s+)(\d{1,2})")


def kickoff_utc(fixture: Fixture) -> datetime:
    """Return the fixture's kick-off as an aware UTC datetime.

    Raises ValueError if the kick-off time is ``"TBD"`` (defensive:
    group-stage rows never are, but knockout rows can be).
    """
    time_et = fixture["time_et"]
    if time_et == "TBD":
        raise ValueError(f"match {fixture['match_id']} has no confirmed kick-off time")
    local = datetime.strptime(f"{fixture['date']} {time_et}", "%Y-%m-%d %H:%M")
    return local.replace(tzinfo=ET_OFFSET).astimezone(UTC)


def bettable_fixtures(now_utc: datetime) -> list[Fixture]:
    """Group-stage fixtures dated today in ET that have not kicked off.

    ``now_utc`` must be timezone-aware.
    """
    today_et = now_utc.astimezone(ET_OFFSET).date().isoformat()
    return [
        fixture
        for fixture in GROUP_STAGE_FIXTURES
        if fixture["date"] == today_et and kickoff_utc(fixture) > now_utc
    ]


def outcome_from_score(home: int, away: int) -> Outcome:
    """Derive the match outcome from a final score."""
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def payout(stake: int) -> int:
    """Coins credited for a winning bet: floor(stake * 1.5), integer math."""
    return stake * 3 // 2


def parse_score(raw: str) -> tuple[int, int] | None:
    """Parse a final score like ``2-1``, ``2:1`` or ``2 1``.

    Returns None on anything else (garbage, negatives, empty input) —
    parsers never crash on user input.
    """
    match = _SCORE_RE.fullmatch(raw.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_stake(raw: str, balance: int) -> int | None:
    """Parse a stake: an int in ``[1, balance]``, or ``all`` for the balance.

    Returns None on anything else.
    """
    text = raw.strip().lower()
    if text == "all":
        stake = balance
    else:
        try:
            stake = int(text)
        except ValueError:
            return None
    if 1 <= stake <= balance:
        return stake
    return None
