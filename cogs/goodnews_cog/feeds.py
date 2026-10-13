"""RSS feed definitions and parser for the $goodnews command.

Fetches publisher-provided teasers only — no full article scraping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from textwrap import shorten
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup
from lxml import etree

from db.news import NEWS_MAX_AGE, NewsArticle

_MAX_BODY = 2 * 1024 * 1024  # 2 MiB
_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=15)

_TITLE_MAX = 250
_EXCERPT_MAX = 350
_URL_MAX = 512

# Case-insensitive category slugs that must be excluded.
_EXCLUDED_CATEGORIES: frozenset[str] = frozenset(
    {"opinion", "opinión", "sponsored", "promoted", "advertorial"}
)

# Characters forbidden in link URLs.
_BAD_URL_CHARS = re.compile(r"[\s\x00-\x1f\x7f<>]")


@dataclass(frozen=True, slots=True)
class Feed:
    """A fixed publisher feed and its native language."""
    url: str
    language: str
    source_name: str

    @property
    def host(self) -> str:
        """Return the publisher hostname used to validate article links."""
        return urlparse(self.url).hostname or ""


FEEDS: dict[str, Feed] = {
    "en": Feed(
        url="https://www.positive.news/feed/",
        language="en",
        source_name="Positive News",
    ),
    "es": Feed(
        url="https://noticiaspositivas.es/feed/",
        language="es",
        source_name="Noticias Positivas",
    ),
}


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

def _is_wp_footer(text: str) -> bool:
    """Return True if paragraph text is a WordPress 'appeared first on' attribution."""
    t = text.strip()
    return (
        (t.startswith("The post ") and "appeared first on" in t)
        or (t.startswith("La entrada ") and "se public" in t and "primero en" in t)
    )


def _strip_html(raw: str) -> str:
    """Strip HTML, remove scripts/styles/WP footer, decode entities, collapse whitespace."""
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for p in soup.find_all("p"):
        if _is_wp_footer(p.get_text(" ", strip=True)):
            p.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def _valid_url(url: str, feed: Feed) -> bool:
    """Return True for a safe HTTPS article URL on the publisher's host."""
    if not url or len(url) > _URL_MAX:
        return False
    if _BAD_URL_CHARS.search(url):
        return False
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == feed.host
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw.strip())
        return dt if dt.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

class _SkipItem(Exception):
    """Signal to skip a single item without aborting the whole feed."""


def _parse_item(
    item: etree._Element,
    feed: Feed,
    *,
    now: datetime,
    oldest: datetime,
) -> NewsArticle:
    # Categories — cheap filter first.
    categories = {(el.text or "").strip().lower() for el in item.iterfind("category")}
    if categories & _EXCLUDED_CATEGORIES:
        raise _SkipItem("excluded category")

    # Link
    link_el = item.find("link")
    url = (link_el.text or "").strip() if link_el is not None else ""
    if not _valid_url(url, feed):
        raise _SkipItem("invalid link")

    # Date
    pub_el = item.find("pubDate")
    pub_date = _parse_date(pub_el.text if pub_el is not None else None)
    if pub_date is None:
        raise _SkipItem("missing or invalid pubDate")
    if pub_date > now:
        raise _SkipItem("future pubDate")
    if pub_date < oldest:
        raise _SkipItem("article older than NEWS_MAX_AGE")

    # Title — may be CDATA HTML or plain text; strip either way.
    title_el = item.find("title")
    raw_title = (title_el.text or "") if title_el is not None else ""
    title = shorten(_strip_html(raw_title), width=_TITLE_MAX, placeholder="…")
    if not title:
        raise _SkipItem("empty title")

    # Description → excerpt teaser (publisher HTML, WP footer removed).
    desc_el = item.find("description")
    raw_desc = (desc_el.text or "") if desc_el is not None else ""
    excerpt = shorten(_strip_html(raw_desc), width=_EXCERPT_MAX, placeholder="…")
    if not excerpt:
        raise _SkipItem("empty excerpt")

    return NewsArticle(
        url=url,
        language=feed.language,
        source_name=feed.source_name,
        title=title,
        excerpt=excerpt,
        published_at=pub_date,
    )


def parse_feed(data: bytes, feed: Feed, *, now: datetime) -> list[NewsArticle]:
    """Parse RSS *data* bytes and return a filtered list of :class:`NewsArticle`.

    Raises :class:`ValueError` for a malformed document or missing RSS
    structure.  Invalid individual items are silently skipped.  No network
    access or external entity resolution is performed.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Malformed RSS document: {exc}") from exc

    if root.tag != "rss":
        raise ValueError(f"Expected <rss> root element, got <{root.tag}>")
    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS document is missing a <channel> element")

    oldest = now - NEWS_MAX_AGE
    articles: list[NewsArticle] = []
    for item in channel.iterfind("item"):
        try:
            articles.append(_parse_item(item, feed, now=now, oldest=oldest))
        except _SkipItem:
            continue
    return articles


async def fetch_feed(session: aiohttp.ClientSession, feed: Feed) -> list[NewsArticle]:
    """Fetch *feed* over HTTP and return parsed articles.

    HTTP-level failures raise :class:`ValueError`.  Network / timeout errors
    from *session* propagate unchanged.
    """
    async with session.get(
        feed.url,
        timeout=_FETCH_TIMEOUT,
    ) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} from {feed.url}")
        content_length = resp.content_length
        if content_length is not None and content_length > _MAX_BODY:
            raise ValueError(f"Feed too large: {content_length} bytes")
        data = bytearray()
        async for chunk in resp.content.iter_chunked(65536):
            data.extend(chunk)
            if len(data) > _MAX_BODY:
                raise ValueError("Feed response exceeds 2 MiB limit")

    return parse_feed(bytes(data), feed, now=datetime.now(UTC))
