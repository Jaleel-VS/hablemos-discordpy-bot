"""Bilingual good-news article store and per-channel sequential delivery."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from db import DatabaseMixin

NEWS_MAX_AGE = timedelta(days=90)


@dataclass(frozen=True, slots=True)
class NewsArticle:
    """One good-news article fetched from an RSS feed."""

    url: str
    language: str
    source_name: str
    title: str
    excerpt: str
    published_at: datetime


class NewsMixin(DatabaseMixin):
    """Store good-news articles and draw newest-first without per-channel repeats."""

    async def store_good_news(self, articles: list[NewsArticle]) -> None:
        """UPSERT articles transactionally, preserving each channel's seen state."""
        if not articles:
            return
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.executemany(
                """
                INSERT INTO good_news_articles
                    (url, language, source_name, title, excerpt, published_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (url) DO UPDATE SET
                    language     = EXCLUDED.language,
                    source_name  = EXCLUDED.source_name,
                    title        = EXCLUDED.title,
                    excerpt      = EXCLUDED.excerpt,
                    published_at = EXCLUDED.published_at
                """,
                [
                    (a.url, a.language, a.source_name, a.title, a.excerpt, a.published_at)
                    for a in articles
                ],
            )

    async def prune_good_news(self) -> None:
        """Delete articles older than NEWS_MAX_AGE; good_news_seen rows cascade."""
        await self._execute(
            "DELETE FROM good_news_articles WHERE published_at < NOW() - $1::interval",
            NEWS_MAX_AGE,
        )

    async def next_good_news(self, channel_id: int, language: str) -> NewsArticle:
        """Reserve the newest unseen recent article in *language* for *channel_id*.

        Serializes concurrent draws via a per-channel row lock.  Only articles
        published within NEWS_MAX_AGE and not in the future qualify.  Raises
        ``LookupError`` when no qualifying unseen articles remain — no cycle
        reset, no repeat.
        """
        async with self._pool().acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO good_news_channels (channel_id) VALUES ($1) ON CONFLICT DO NOTHING",
                channel_id,
            )
            # Row-lock the channel row to serialize concurrent draws for this channel.
            await conn.fetchval(
                "SELECT channel_id FROM good_news_channels WHERE channel_id = $1 FOR UPDATE",
                channel_id,
            )
            row = await conn.fetchrow(
                """
                SELECT a.*
                FROM good_news_articles a
                WHERE a.language = $2
                  AND a.published_at <= NOW()
                  AND a.published_at >= NOW() - $3::interval
                  AND NOT EXISTS (
                      SELECT 1 FROM good_news_seen s
                      WHERE s.channel_id = $1 AND s.url = a.url
                  )
                ORDER BY a.published_at DESC
                LIMIT 1
                """,
                channel_id, language, NEWS_MAX_AGE,
            )
            if row is None:
                raise LookupError("No unread recent good-news articles are available")
            article = NewsArticle(**dict(row))
            await conn.execute(
                "INSERT INTO good_news_seen (channel_id, url) VALUES ($1, $2)",
                channel_id, article.url,
            )
            return article
