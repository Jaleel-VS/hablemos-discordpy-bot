"""Unit tests for cogs/goodnews_cog/feeds.py.

Deterministic boundary tests only — no network, no mocked forwarding.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape

import pytest

from cogs.goodnews_cog.feeds import FEEDS, Feed, parse_feed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EN = FEEDS["en"]
_NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)
_PUB = "Tue, 13 Oct 2026 09:00:00 +0000"


def _rss(items: str, *, root: str = '<rss version="2.0">') -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'{root}<channel><title>T</title>{items}</channel></rss>'
    ).encode()


def _item(
    title: str = "Good title",
    link: str = "https://www.positive.news/story/",
    pub: str = _PUB,
    desc: str = "A helpful paragraph about something positive.",
    categories: list[str] | None = None,
) -> str:
    cats = "".join(f"<category><![CDATA[{c}]]></category>" for c in (categories or []))
    return (
        "<item>"
        f"<title><![CDATA[{title}]]></title>"
        f"<link>{escape(link)}</link>"
        f"<pubDate>{pub}</pubDate>"
        f"<description><![CDATA[{desc}]]></description>"
        f"{cats}"
        "</item>"
    )


def _parse(xml: bytes, feed: Feed = _EN) -> list:
    return parse_feed(xml, feed, now=_NOW)


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------

def test_malformed_xml_raises() -> None:
    with pytest.raises(ValueError, match="Malformed"):
        _parse(b"<not valid xml <<")


def test_wrong_root_raises() -> None:
    with pytest.raises(ValueError, match="<rss>"):
        _parse(b'<?xml version="1.0"?><feed><channel></channel></feed>')


def test_missing_channel_raises() -> None:
    with pytest.raises(ValueError, match="<channel>"):
        _parse(b'<?xml version="1.0"?><rss version="2.0"></rss>')


# ---------------------------------------------------------------------------
# XXE / untrusted XML
# ---------------------------------------------------------------------------

def test_external_entity_not_resolved() -> None:
    """DOCTYPE with SYSTEM entity must not trigger file reads; item skipped."""
    doc = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b'<rss version="2.0"><channel>'
        b"<item>"
        b"<title>&xxe;</title>"
        b"<link>https://www.positive.news/story/</link>"
        b"<pubDate>Mon, 13 Oct 2026 09:00:00 +0000</pubDate>"
        b"<description>fine</description>"
        b"</item>"
        b"</channel></rss>"
    )
    # Item title resolves to None (entity not expanded) → skipped, no error raised.
    articles = _parse(doc)
    assert articles == []


# ---------------------------------------------------------------------------
# Date filters
# ---------------------------------------------------------------------------

def test_future_date_skipped() -> None:
    future = "Wed, 14 Oct 2026 09:00:00 +0000"  # one day ahead of _NOW
    assert _parse(_rss(_item(pub=future))) == []


def test_article_older_than_max_age_skipped() -> None:
    old = (_NOW - timedelta(days=90, seconds=1)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    assert _parse(_rss(_item(pub=old))) == []


def test_exactly_at_max_age_boundary_accepted() -> None:
    boundary = _NOW - timedelta(days=90)
    pub_str = boundary.strftime("%a, %d %b %Y %H:%M:%S +0000")
    articles = _parse(_rss(_item(pub=pub_str)))
    assert [article.published_at for article in articles] == [boundary]


def test_missing_pubdate_skipped() -> None:
    item = (
        "<item>"
        "<title><![CDATA[Good]]></title>"
        "<link>https://www.positive.news/story/</link>"
        "<description><![CDATA[desc]]></description>"
        "</item>"
    )
    assert _parse(_rss(item)) == []


def test_invalid_pubdate_skipped() -> None:
    assert _parse(_rss(_item(pub="not-a-date"))) == []


# ---------------------------------------------------------------------------
# Link validation
# ---------------------------------------------------------------------------

def test_http_link_rejected() -> None:
    assert _parse(_rss(_item(link="http://www.positive.news/story/"))) == []


def test_wrong_host_rejected() -> None:
    assert _parse(_rss(_item(link="https://evil.example.com/story/"))) == []


def test_userinfo_in_url_rejected() -> None:
    assert _parse(_rss(_item(link="https://user@www.positive.news/story/"))) == []


def test_whitespace_in_url_rejected() -> None:
    assert _parse(_rss(_item(link="https://www.positive.news/sto ry/"))) == []


def test_angle_bracket_in_url_rejected() -> None:
    assert _parse(_rss(_item(link="https://www.positive.news/<script>"))) == []


def test_url_over_512_chars_rejected() -> None:
    long_path = "a" * 500
    assert _parse(_rss(_item(link=f"https://www.positive.news/{long_path}"))) == []


# ---------------------------------------------------------------------------
# Opinion / promoted category filter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cat", ["Opinion", "Opinión", "Sponsored", "Promoted", "Advertorial"])
def test_excluded_category_skipped(cat: str) -> None:
    assert _parse(_rss(_item(categories=[cat]))) == []


def test_non_excluded_category_accepted() -> None:
    articles = _parse(_rss(_item(categories=["Environment", "Society"])))
    assert len(articles) == 1


# ---------------------------------------------------------------------------
# HTML stripping / XSS safety
# ---------------------------------------------------------------------------

def test_html_tags_stripped_from_excerpt() -> None:
    desc = "<p>Good <strong>news</strong> today!</p>"
    articles = _parse(_rss(_item(desc=desc)))
    assert "<" not in articles[0].excerpt
    assert "Good news today!" in articles[0].excerpt


def test_script_tag_stripped() -> None:
    desc = '<p>Clean text.</p><script>alert("xss")</script>'
    articles = _parse(_rss(_item(desc=desc)))
    assert "script" not in articles[0].excerpt.lower()
    assert "alert" not in articles[0].excerpt


def test_wordpress_footer_stripped_english() -> None:
    desc = (
        "<p>Real content here.</p>"
        '<p>The post <a href="https://www.positive.news/story/">Title</a> '
        'appeared first on <a href="https://www.positive.news">Positive News</a>.</p>'
    )
    articles = _parse(_rss(_item(desc=desc)))
    assert "appeared first on" not in articles[0].excerpt
    assert "Real content here." in articles[0].excerpt


def test_wordpress_footer_stripped_spanish() -> None:
    es = FEEDS["es"]
    desc = (
        "<p>Contenido real aquí.</p>"
        '<p>La entrada <a href="https://noticiaspositivas.es/historia/">Título</a> '
        "se publicó primero en "
        '<a href="https://noticiaspositivas.es">Noticias Positivas</a>.</p>'
    )
    item_xml = _item(
        link="https://noticiaspositivas.es/historia/",
        desc=desc,
    )
    articles = parse_feed(_rss(item_xml), es, now=_NOW)
    assert "se publicó primero en" not in articles[0].excerpt
    assert "Contenido real aquí." in articles[0].excerpt


def test_html_entities_decoded() -> None:
    desc = "<p>It&rsquo;s &amp; great &mdash; today.</p>"
    articles = _parse(_rss(_item(desc=desc)))
    assert "&" not in articles[0].excerpt or "amp" not in articles[0].excerpt
    assert "great" in articles[0].excerpt


# ---------------------------------------------------------------------------
# Length caps
# ---------------------------------------------------------------------------

def test_excerpt_capped_at_350_chars() -> None:
    long_desc = f"<p>{'x' * 800}</p>"
    articles = _parse(_rss(_item(desc=long_desc)))
    assert len(articles[0].excerpt) <= 350


def test_title_capped_at_250_chars() -> None:
    long_title = "T" * 600
    articles = _parse(_rss(_item(title=long_title)))
    assert len(articles[0].title) <= 250


# ---------------------------------------------------------------------------
# Empty title / excerpt skipped
# ---------------------------------------------------------------------------

def test_empty_title_after_strip_skipped() -> None:
    assert _parse(_rss(_item(title="<span></span>"))) == []


def test_empty_excerpt_after_strip_skipped() -> None:
    assert _parse(_rss(_item(desc="<p></p>"))) == []


# ---------------------------------------------------------------------------
# Happy path — valid item round-trip
# ---------------------------------------------------------------------------

def test_valid_item_parsed_correctly() -> None:
    articles = _parse(_rss(_item()))
    assert len(articles) == 1
    a = articles[0]
    assert a.url == "https://www.positive.news/story/"
    assert a.language == "en"
    assert a.source_name == "Positive News"
    assert a.title == "Good title"
    assert a.published_at.tzinfo is not None


def test_multiple_items_returned() -> None:
    item2 = _item(
        title="Second story",
        link="https://www.positive.news/story2/",
    )
    articles = _parse(_rss(_item() + item2))
    assert len(articles) == 2


def test_invalid_item_among_valid_does_not_abort() -> None:
    bad = _item(link="http://www.positive.news/bad/")  # http → rejected
    good = _item(
        title="Fine story",
        link="https://www.positive.news/fine/",
    )
    articles = _parse(_rss(bad + good))
    assert len(articles) == 1
    assert articles[0].title == "Fine story"
