"""Real-Postgres integration tests for NewsMixin good-news delivery guarantees.

Run with TEST_DATABASE_URL pointing at a server where the current user can
CREATE DATABASE.  Each test runs against a freshly created, isolated database
so it is safe to run in parallel with any other test suite.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest

from db import Database
from db.news import NEWS_MAX_AGE, NewsArticle
from db.schema import initialize_schema

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)


def _article(
    url: str,
    language: str = "en",
    *,
    offset: timedelta = timedelta(hours=1),
    source: str = "Positive News",
) -> NewsArticle:
    """Return a NewsArticle published *offset* ago (default 1 h ago)."""
    return NewsArticle(
        url=f"https://www.positive.news/{url}",
        language=language,
        source_name=source,
        title=f"Title {url}",
        excerpt=f"Excerpt for {url}.",
        published_at=_NOW - offset,
    )


async def _seed(db: Database, articles: list[NewsArticle]) -> None:
    await db.store_good_news(articles)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def news_db() -> AsyncIterator[Database]:
    """Isolated database; skipped unless TEST_DATABASE_URL is set."""
    if not TEST_DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL to run good-news DB integration tests")
    db_name = "news_test_" + uuid4().hex
    admin = await asyncpg.connect(TEST_DATABASE_URL)
    database = Database(TEST_DATABASE_URL)
    await admin.execute(f'CREATE DATABASE "{db_name}"')
    try:
        database.pool = await asyncpg.create_pool(
            TEST_DATABASE_URL, min_size=1, max_size=10, database=db_name
        )
        await initialize_schema(database._pool())
        yield database
    finally:
        await database.close()
        await admin.execute(f'DROP DATABASE "{db_name}"')
        await admin.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_concurrent_draws_one_per_article(news_db: Database) -> None:
    """Concurrent draws for the same channel/language each receive a distinct article."""
    articles = [_article(f"story-{i}", offset=timedelta(hours=i + 1)) for i in range(8)]
    await _seed(news_db, articles)

    draws = await asyncio.gather(*(news_db.next_good_news(100, "en") for _ in articles))
    urls = [a.url for a in draws]
    assert len(urls) == len(set(urls)), "duplicate URL delivered in concurrent draws"
    assert set(urls) == {a.url for a in articles}


async def test_language_and_freshness_isolation(news_db: Database) -> None:
    """Language filter and age cutoff are both respected."""
    en = _article("en-1", "en", offset=timedelta(days=1))
    es = _article("es-1", "es", offset=timedelta(days=60))
    stale = _article("stale", "en", offset=NEWS_MAX_AGE + timedelta(minutes=1))
    future = _article("future", "en", offset=-timedelta(hours=1))  # published_at in future
    await _seed(news_db, [en, es, stale, future])

    got = await news_db.next_good_news(100, "en")
    assert got.url == en.url
    assert got.language == "en"

    # Spanish channel gets only the Spanish article
    got_es = await news_db.next_good_news(200, "es")
    assert got_es.url == es.url

    # No more English articles for channel 100
    with pytest.raises(LookupError):
        await news_db.next_good_news(100, "en")

    await news_db._execute(
        "UPDATE good_news_articles SET published_at = NOW() - INTERVAL '91 days' WHERE url = $1",
        en.url,
    )
    await news_db.prune_good_news()
    assert await news_db._fetchval("SELECT count(*) FROM good_news_seen WHERE channel_id = 100") == 0
    assert await news_db._fetchval("SELECT count(*) FROM good_news_articles WHERE url = $1", en.url) == 0
    assert await news_db._fetchval("SELECT count(*) FROM good_news_articles WHERE url = $1", es.url) == 1


async def test_exhaustion_raises_not_cycles(news_db: Database) -> None:
    """After all articles are seen, LookupError is raised — no silent cycle reset."""
    articles = [_article(f"a{days}", offset=timedelta(days=days)) for days in (60, 1, 30)]
    await _seed(news_db, articles)
    await news_db.prune_good_news()

    draws = [await news_db.next_good_news(100, "en") for _ in articles]
    assert [article.url for article in draws] == [articles[1].url, articles[2].url, articles[0].url]

    with pytest.raises(LookupError):
        await news_db.next_good_news(100, "en")

    # Seen count stays at 3 — nothing was reset.
    count = await news_db._fetchval(
        "SELECT count(*) FROM good_news_seen WHERE channel_id = 100"
    )
    assert count == 3


async def test_reseed_reconnect_no_reset(news_db: Database) -> None:
    """Re-storing existing articles (upsert) does not clear any channel's seen state."""
    articles = [_article(f"r{i}", offset=timedelta(hours=i + 1)) for i in range(4)]
    await _seed(news_db, articles)

    first = await news_db.next_good_news(100, "en")

    # Simulate a feed re-fetch: upsert the same articles again.
    await _seed(news_db, articles)
    db_name = await news_db._fetchval("SELECT current_database()")
    await news_db.close()
    news_db.pool = await asyncpg.create_pool(
        TEST_DATABASE_URL, min_size=1, max_size=2, database=db_name,
    )

    # Seen row for 'first' must still exist.
    still_seen = await news_db._fetchval(
        "SELECT count(*) FROM good_news_seen WHERE channel_id = 100 AND url = $1",
        first.url,
    )
    assert still_seen == 1, "re-seeding erased a seen row"

    # Remaining draws should not include 'first'.
    remaining = [await news_db.next_good_news(100, "en") for _ in range(3)]
    assert first.url not in {a.url for a in remaining}


async def test_newer_article_appears_after_exhaustion(news_db: Database) -> None:
    """A freshly stored article is delivered after exhaustion without resetting seen rows."""
    old = _article("old", offset=timedelta(days=2))
    await _seed(news_db, [old])
    await news_db.next_good_news(100, "en")

    # Old articles exhausted.
    with pytest.raises(LookupError):
        await news_db.next_good_news(100, "en")

    # A new article arrives.
    new = _article("new", offset=timedelta(minutes=30))
    await _seed(news_db, [new])

    got = await news_db.next_good_news(100, "en")
    assert got.url == new.url

    # Still exhausted after drawing the new one.
    with pytest.raises(LookupError):
        await news_db.next_good_news(100, "en")
