"""Networked ESPN scoreboard access for the betting cog.

Thin aiohttp layer over the parsing helpers in `results.py`. The raw
scoreboard fetch is deliberately uncached (the results poller needs
fresh completion status); the odds fetch is cached in 10-minute buckets
because lines move slowly pre-match and the panel re-renders often.
"""
import logging
from datetime import UTC, datetime
from decimal import Decimal

import aiohttp

from cogs.utils.async_cache import async_cache
from cogs.wcpredict_cog.fixtures import Fixture

from . import results

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 15
ODDS_CACHE_BUCKET_SECONDS = 600


async def fetch_scoreboard(date_str: str) -> dict | None:
    """Fetch one ET-day's scoreboard JSON; None on any network failure."""
    url = results.ESPN_SCOREBOARD_URL.format(date=date_str)
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(url) as response,
        ):
            if response.status != 200:
                logger.warning(
                    "ESPN scoreboard returned HTTP %s for %s", response.status, date_str,
                )
                return None
            return await response.json()
    except (aiohttp.ClientError, TimeoutError) as exc:
        logger.warning("ESPN scoreboard fetch failed for %s: %s", date_str, exc)
        return None


@async_cache(maxsize=8)
async def _fetch_odds_bucket(date_str: str, bucket: int) -> dict[int, results.MatchOdds]:
    """Odds for every match on an ET day, keyed by match_id.

    `bucket` partitions the LRU cache into time windows (the cache has
    no TTL of its own). Failures return {} — callers fall back to flat
    odds — and async_cache retries failed tasks on the next call.
    """
    payload = await fetch_scoreboard(date_str)
    if payload is None:
        return {}
    return results.match_odds(payload, results.FIXTURES)


async def fetch_match_odds(
    fixtures: list[Fixture], multiplier: Decimal | None = None,
) -> dict[int, results.MatchOdds]:
    """Current decimal odds for the given fixtures (10-min cache).

    When `multiplier` is given, every published line is scaled by it
    (the house odds boost) before being returned. The raw ESPN prices
    stay cached unscaled, so changing the multiplier takes effect on the
    next render without busting the cache.
    """
    if not fixtures:
        return {}
    bucket = int(datetime.now(UTC).timestamp()) // ODDS_CACHE_BUCKET_SECONDS
    odds: dict[int, results.MatchOdds] = {}
    for date_str in sorted({f["date"].replace("-", "") for f in fixtures}):
        odds.update(await _fetch_odds_bucket(date_str, bucket))
    wanted = {f["match_id"] for f in fixtures}
    selected = {mid: o for mid, o in odds.items() if mid in wanted}
    if multiplier is not None and multiplier != 1:
        selected = {
            mid: results.apply_odds_multiplier(o, multiplier)
            for mid, o in selected.items()
        }
    return selected


async def fetch_knockout_resolutions(
    unresolved: list[Fixture],
) -> list[results.KnockoutResolution]:
    """Resolve knockout teams from ESPN's scheduled events (uncached).

    Fetches the scoreboard for each date the given unresolved knockout
    fixtures fall on and asks `results.knockout_resolutions` to match them
    by kickoff, returning only fixtures ESPN has fully decided (both real
    teams). Uncached so freshly-decided ties are picked up promptly; the
    set is small (one fetch per knockout date) and only runs while
    unresolved knockouts remain.
    """
    if not unresolved:
        return []
    out: list[results.KnockoutResolution] = []
    for date_str in sorted({f["date"].replace("-", "") for f in unresolved}):
        payload = await fetch_scoreboard(date_str)
        if payload is None:
            continue
        same_day = [f for f in unresolved if f["date"].replace("-", "") == date_str]
        out.extend(results.knockout_resolutions(payload, same_day))
    return out
