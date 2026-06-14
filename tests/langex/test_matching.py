"""Tests for the pure language-exchange match-scoring engine."""
from datetime import datetime, timedelta, timezone

from cogs.langex_cog.matching import Match, rank_matches

NOW = datetime(2026, 6, 14, tzinfo=timezone.utc)


def _post(user_id, offer, seek, *, level="B1", region="north_america",
          about="", want="", interests="", msg=None, posted_days_ago=1):
    """Build an exchange-post record like the DB returns."""
    return {
        "user_id": user_id,
        "message_id": msg if msg is not None else user_id + 1000,
        "channel_id": 999,
        "posted_at": NOW - timedelta(days=posted_days_ago),
        "post_data": {
            "offer_lang": offer,
            "seek_lang": seek,
            "seek_level": level,
            "region": region,
            "prefer_dm": True,
            "about_text": about,
            "want_text": want,
            "interests": interests,
        },
    }


def _me(offer, seek, **kw):
    me = _post(1, offer, seek, **kw)
    return {"user_id": 1, "post_data": me["post_data"]}


# RECIPROCITY (the hard requirement)

def test_reciprocal_match_is_returned():
    me = _me("english", "spanish")
    others = [_post(2, "spanish", "english")]
    result = rank_matches(me, others, now=NOW)
    assert [m.user_id for m in result] == [2]


def test_one_way_offer_is_not_a_match():
    # They offer what I seek, but they don't want what I offer.
    me = _me("english", "spanish")
    others = [_post(2, "spanish", "french")]
    assert rank_matches(me, others, now=NOW) == []


def test_one_way_seek_is_not_a_match():
    # They want what I offer, but they don't offer what I seek.
    me = _me("english", "spanish")
    others = [_post(2, "french", "english")]
    assert rank_matches(me, others, now=NOW) == []


def test_same_language_pair_never_matches():
    me = _me("english", "spanish")
    others = [_post(2, "english", "spanish")]  # same direction, not reciprocal
    assert rank_matches(me, others, now=NOW) == []


def test_self_is_excluded():
    me = _me("english", "spanish")
    others = [_post(1, "spanish", "english")]  # same user_id as me
    assert rank_matches(me, others, now=NOW) == []


# RANKING

def test_region_exact_beats_region_far():
    me = _me("english", "spanish", region="south_america")
    near = _post(2, "spanish", "english", region="south_america", posted_days_ago=10)
    far = _post(3, "spanish", "english", region="east_asia", posted_days_ago=10)
    result = rank_matches(me, [far, near], now=NOW)
    assert [m.user_id for m in result] == [2, 3]


def test_region_bucket_beats_other_bucket():
    me = _me("english", "spanish", region="north_america")
    same_bucket = _post(2, "spanish", "english", region="south_america", posted_days_ago=10)
    other_bucket = _post(3, "spanish", "english", region="east_asia", posted_days_ago=10)
    result = rank_matches(me, [other_bucket, same_bucket], now=NOW)
    assert [m.user_id for m in result] == [2, 3]


def test_shared_interests_boost_ranking():
    me = _me("english", "spanish", region="north_america",
             interests="climbing photography astronomy")
    shared = _post(2, "spanish", "english", region="east_asia",
                   interests="astronomy climbing", posted_days_ago=10)
    none = _post(3, "spanish", "english", region="east_asia",
                 interests="cooking knitting", posted_days_ago=10)
    result = rank_matches(me, [none, shared], now=NOW)
    assert result[0].user_id == 2


def test_recency_boosts_ranking_when_otherwise_equal():
    me = _me("english", "spanish", region="north_america")
    recent = _post(2, "spanish", "english", region="east_asia", posted_days_ago=2)
    old = _post(3, "spanish", "english", region="east_asia", posted_days_ago=60)
    result = rank_matches(me, [old, recent], now=NOW)
    assert [m.user_id for m in result] == [2, 3]


def test_level_fit_rewards_close_levels():
    # Me: beginner (A1). Close-level partner should outrank a near-native.
    me = _me("english", "spanish", level="A1", region="north_america")
    close = _post(2, "spanish", "english", level="A2", region="east_asia", posted_days_ago=10)
    far = _post(3, "spanish", "english", level="C2", region="east_asia", posted_days_ago=10)
    result = rank_matches(me, [far, close], now=NOW)
    assert result[0].user_id == 2


# OUTPUT SHAPE & LIMITS

def test_limit_caps_results():
    me = _me("english", "spanish")
    others = [_post(i, "spanish", "english") for i in range(2, 20)]
    result = rank_matches(me, others, now=NOW, limit=5)
    assert len(result) == 5


def test_match_carries_jump_link_fields():
    me = _me("english", "spanish")
    others = [_post(2, "spanish", "english", msg=555)]
    (match,) = rank_matches(me, others, now=NOW)
    assert isinstance(match, Match)
    assert match.message_id == 555
    assert match.channel_id == 999
    assert match.offer_lang == "spanish"
    assert match.seek_lang == "english"


def test_missing_post_data_is_handled():
    me = _me("english", "spanish")
    others = [{"user_id": 2, "message_id": 1, "channel_id": 1, "posted_at": NOW, "post_data": None}]
    assert rank_matches(me, others, now=NOW) == []


def test_naive_posted_at_is_treated_as_utc():
    me = _me("english", "spanish")
    naive = _post(2, "spanish", "english")
    naive["posted_at"] = datetime(2026, 6, 13)  # tz-naive, ~1 day ago
    # Should not raise and should still match.
    result = rank_matches(me, [naive], now=NOW)
    assert [m.user_id for m in result] == [2]


def test_empty_pool_returns_empty():
    me = _me("english", "spanish")
    assert rank_matches(me, [], now=NOW) == []
