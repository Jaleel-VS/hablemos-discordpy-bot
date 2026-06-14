"""Pure match-scoring engine for language exchange.

No Discord or DB dependencies — takes plain ``post_data`` dicts and
returns ranked matches, so the matching logic is fully unit-testable.

A *match* is reciprocal by definition: I offer the language you want to
learn, **and** you offer the language I want to learn. Among reciprocal
candidates, ranking favors region proximity, shared interests, a good
level fit, and recency (active posters first).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .config import PROFICIENCY_LEVELS, REGION_BUCKET

# Level value → rank index (0 = strongest/C2). Used for level-fit scoring.
_LEVEL_INDEX: dict[str, int] = {value: i for i, (_label, value) in enumerate(PROFICIENCY_LEVELS)}

# Scoring weights.
_W_REGION_EXACT = 3
_W_REGION_BUCKET = 1
_W_INTEREST_EACH = 1
_W_INTEREST_CAP = 4
_W_LEVEL_FIT = 2
_W_RECENT_7D = 2
_W_RECENT_30D = 1

# Stopwords stripped before interest-keyword overlap.
_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "you", "your", "are", "but", "not", "can",
    "want", "like", "love", "some", "any", "all", "this", "that", "they",
    "have", "from", "about", "would", "could", "into", "also", "just",
    "looking", "someone", "native", "speaker", "language", "languages",
    "practice", "practise", "learn", "learning", "improve", "help", "talk",
    "speak", "speaking", "spanish", "english", "level", "time", "zone",
})

_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


@dataclass(frozen=True)
class Match:
    """A scored, reciprocal candidate."""

    user_id: int
    message_id: int
    channel_id: int
    offer_lang: str
    seek_lang: str
    seek_level: str | None
    region: str | None
    prefer_dm: bool
    score: int


def _keywords(text: str | None) -> set[str]:
    """Lowercased content words from free text, minus stopwords/short words."""
    if not text:
        return set()
    return {
        w.lower()
        for w in _WORD_RE.findall(text)
        if len(w) >= 4 and w.lower() not in _STOPWORDS
    }


def _interest_text(data: dict) -> str:
    """Concatenate the free-text fields used for interest overlap."""
    parts = [data.get("about_text") or "", data.get("want_text") or "", data.get("interests") or ""]
    return " ".join(parts)


def _is_reciprocal(me: dict, them: dict) -> bool:
    """True when each offers the language the other seeks."""
    return (
        me.get("offer_lang") is not None
        and me.get("seek_lang") is not None
        and me["offer_lang"] == them.get("seek_lang")
        and them.get("offer_lang") == me["seek_lang"]
    )


def _recency_points(posted_at: datetime | None, now: datetime) -> int:
    if posted_at is None:
        return 0
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    age = now - posted_at
    if age <= timedelta(days=7):
        return _W_RECENT_7D
    if age <= timedelta(days=30):
        return _W_RECENT_30D
    return 0


def _score(me: dict, them: dict, my_interests: set[str], posted_at: datetime | None, now: datetime) -> int:
    score = 0

    # Region proximity.
    my_region = me.get("region")
    their_region = them.get("region")
    if my_region and their_region:
        if my_region == their_region:
            score += _W_REGION_EXACT
        elif REGION_BUCKET.get(my_region) == REGION_BUCKET.get(their_region):
            score += _W_REGION_BUCKET

    # Shared interests (keyword overlap, capped).
    overlap = my_interests & _keywords(_interest_text(them))
    score += min(len(overlap) * _W_INTEREST_EACH, _W_INTEREST_CAP)

    # Level fit: reward partners whose *target* level is close to mine, so a
    # beginner is paired with someone also early-stage rather than a near-native.
    my_level = me.get("seek_level")
    their_level = them.get("seek_level")
    if (
        my_level in _LEVEL_INDEX
        and their_level in _LEVEL_INDEX
        and abs(_LEVEL_INDEX[my_level] - _LEVEL_INDEX[their_level]) <= 1
    ):
        score += _W_LEVEL_FIT

    # Recency — favor people who posted recently (more likely active).
    score += _recency_points(posted_at, now)

    return score


def rank_matches(
    me: dict,
    others: list[dict],
    *,
    limit: int = 10,
    now: datetime | None = None,
) -> list[Match]:
    """Rank reciprocal partners for ``me`` among ``others``.

    Parameters
    ----------
    me:
        The requesting user's record: ``{"user_id", "post_data": {...}}``.
    others:
        All exchange-post records (each ``{"user_id", "message_id",
        "channel_id", "posted_at", "post_data": {...}}``). The requester is
        skipped automatically.
    limit:
        Maximum number of matches to return.
    now:
        Current time (injected for testability). Defaults to UTC now.

    Returns
    -------
    A list of :class:`Match`, best first. Ties break by recency then user_id
    for stable ordering.
    """
    now = now or datetime.now(UTC)
    my_data = me.get("post_data") or {}
    my_id = me.get("user_id")
    my_interests = _keywords(_interest_text(my_data))

    scored: list[tuple[int, datetime, Match]] = []
    for other in others:
        if other.get("user_id") == my_id:
            continue
        their_data = other.get("post_data") or {}
        if not _is_reciprocal(my_data, their_data):
            continue

        posted_at = other.get("posted_at")
        score = _score(my_data, their_data, my_interests, posted_at, now)
        sort_time = posted_at or datetime.min.replace(tzinfo=UTC)
        scored.append((
            score,
            sort_time,
            Match(
                user_id=other["user_id"],
                message_id=other.get("message_id", 0),
                channel_id=other.get("channel_id", 0),
                offer_lang=their_data.get("offer_lang", ""),
                seek_lang=their_data.get("seek_lang", ""),
                seek_level=their_data.get("seek_level"),
                region=their_data.get("region"),
                prefer_dm=their_data.get("prefer_dm", True),
                score=score,
            ),
        ))

    # Sort by score desc, then most-recent first, then user_id for stability.
    scored.sort(key=lambda t: (-t[0], -t[1].timestamp(), t[2].user_id))
    return [m for _s, _t, m in scored[:limit]]
