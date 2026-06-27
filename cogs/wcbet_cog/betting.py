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
from decimal import Decimal
from typing import Literal

from cogs.wcpredict_cog.fixtures import FIXTURES, Fixture, is_fixture_resolved

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
    """Fixtures open for betting: resolved, not kicked off, within 24 hours.

    A fixture is bettable when it has real (non-placeholder) teams, has not
    kicked off, and kicks off within the next 24 hours. Group-stage rows are
    always resolved; knockout rows become bettable only once an owner fills
    in the real teams via `$wcbetadmin setteam` (until then both sides are
    bracket placeholders and the fixture is skipped).

    Using a lookahead window instead of ET-date comparison handles midnight-ET
    kickoffs (e.g. match 20) that fall on the next calendar day in ET. Rows
    with a "TBD" kickoff are skipped defensively.

    ``now_utc`` must be timezone-aware.
    """
    cutoff = now_utc + timedelta(hours=24)
    out: list[Fixture] = []
    for fixture in FIXTURES:
        if not is_fixture_resolved(fixture):
            continue
        if fixture["time_et"] == "TBD":
            continue
        if now_utc < kickoff_utc(fixture) <= cutoff:
            out.append(fixture)
    return out


def outcome_from_score(home: int, away: int) -> Outcome:
    """Derive the match outcome from a final score."""
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def payout(stake: int, odds: Decimal) -> int:
    """Coins credited for a winning bet: floor(stake * odds).

    Pure integer arithmetic via hundredths — floats never touch money.
    """
    return stake * int(odds * 100) // 100


def combined_odds(odds: list[Decimal]) -> Decimal:
    """Product of decimal odds for a parlay, quantized to 2dp.

    Empty list returns Decimal('1.00') (identity). Uses Decimal throughout
    so the price never touches a float.
    """
    product = Decimal(1)
    for o in odds:
        product *= o
    return product.quantize(Decimal("0.01"))


def parlay_payout(stake: int, odds: list[Decimal]) -> int:
    """Coins credited for a winning parlay: floor(stake * combined_odds).

    Reuses the same hundredths integer math as ``payout`` against the
    pre-combined price, so a single bet and a 1-leg parlay agree.
    """
    return payout(stake, combined_odds(odds))


# Stake quick-pick amounts offered in the panel (filtered to balance).
STAKE_PRESETS = (100, 250, 500, 1_000, 2_500, 5_000)


def stake_presets(balance: int) -> list[int]:
    """Preset stakes affordable at `balance`, plus an all-in amount.

    The balance itself is appended when it is not already a preset, so
    there is always an "all in" choice (empty list when broke).
    """
    if balance < 1:
        return []
    amounts = [preset for preset in STAKE_PRESETS if preset <= balance]
    if balance not in amounts:
        amounts.append(balance)
    return amounts


def parse_score(raw: str) -> tuple[int, int] | None:
    """Parse a final score like ``2-1``, ``2:1`` or ``2 1``.

    Returns None on anything else (garbage, negatives, empty input) —
    parsers never crash on user input.
    """
    match = _SCORE_RE.fullmatch(raw.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def current_streak(recent_settled: list[str]) -> tuple[str, int] | None:
    """Return (status, count) of the current win/loss streak, or None.

    ``recent_settled`` is newest-first statuses ('won'/'lost'). Walks until
    the status flips.
    """
    if not recent_settled:
        return None
    head = recent_settled[0]
    count = 0
    for status in recent_settled:
        if status != head:
            break
        count += 1
    return head, count


def format_player_results(bets: list[dict], label: str | None = None) -> str | None:
    """Format per-player win/loss lines for posting in the notification channel.

    Returns a newline-joined string of mentions, or None if there are no bets.
    """
    if not bets:
        return None
    lines = [
        f"🏆 <@{b['user_id']}> won **{b['payout']:,}** coins"
        if b["won"]
        else f"💸 <@{b['user_id']}> lost their stake"
        for b in bets
    ]
    if label:
        lines.insert(0, f"🏁 **{label}**")
    return "\n".join(lines)


def format_parlay_results(parlays: list[dict]) -> str | None:
    """Format settled-parlay announcement lines, or None if empty.

    Each parlay dict has user_id, won, payout, stake, odds.
    """
    if not parlays:
        return None
    lines = []
    for p in parlays:
        if p["won"]:
            lines.append(
                f"🎰 **Parlay landed!** <@{p['user_id']}> "
                f"{p['stake']:,} → **{p['payout']:,}** @ {p['odds']}x"
            )
        else:
            lines.append(f"💥 **Parlay busted** <@{p['user_id']}> ({p['stake']:,} lost)")
    return "\n".join(lines)


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
