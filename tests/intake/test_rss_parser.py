"""Tests for RSS feed parser."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from distill.intake.config import IntakeConfig, RSSConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.rss import RSSParser, _normalize_url, _strip_html

# ── HTML stripping ──────────────────────────────────────────────────────

class TestStripHtml:
    def test_strips_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        result = _strip_html("&amp; &lt; &gt; &quot; &#39;")
        assert "&" in result
        assert "<" in result
        assert ">" in result

    def test_nbsp(self):
        assert "foo" in _strip_html("foo&nbsp;bar")
        assert "bar" in _strip_html("foo&nbsp;bar")

    def test_collapses_newlines(self):
        result = _strip_html("<p>a</p><p></p><p></p><p></p><p>b</p>")
        assert "\n\n\n" not in result

    def test_empty(self):
        assert _strip_html("") == ""

    def test_br_tags_become_newlines(self):
        result = _strip_html("line one<br>line two<br />line three")
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result
        assert "<br" not in result

    def test_strips_script_tags(self):
        result = _strip_html("<p>Hello</p><script>alert('xss')</script><p>World</p>")
        assert "alert" not in result
        assert "Hello" in result
        assert "World" in result

    def test_strips_style_tags(self):
        result = _strip_html("<style>.foo{color:red}</style><p>Content</p>")
        assert "color" not in result
        assert "Content" in result

    def test_plain_text_passthrough(self):
        assert _strip_html("just plain text") == "just plain text"

    def test_entities_without_tags(self):
        assert _strip_html("A &amp; B") == "A & B"

    def test_complex_html(self):
        html = """
        <div class="article">
            <h1>Title</h1>
            <p>First paragraph with <a href="url">a link</a>.</p>
            <p>Second paragraph.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </div>
        """
        result = _strip_html(html)
        assert "Title" in result
        assert "First paragraph" in result
        assert "a link" in result
        assert "Item 1" in result
        assert "<" not in result


# ── URL normalization ─────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/article/") == "https://example.com/article"

    def test_strips_fragment(self):
        assert _normalize_url("https://example.com/article#section") == "https://example.com/article"

    def test_preserves_path(self):
        assert _normalize_url("https://example.com/a/b/c") == "https://example.com/a/b/c"


# ── Feed URL resolution ────────────────────────────────────────────────

class TestResolveFeeds:
    def test_direct_feeds(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://a.com/feed", "https://b.com/feed"])
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == ["https://a.com/feed", "https://b.com/feed"]

    def test_deduplicates(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://a.com/feed", "https://a.com/feed"])
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == ["https://a.com/feed"]

    def test_strips_whitespace(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["  https://a.com/feed  "])
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == ["https://a.com/feed"]

    def test_reads_feeds_file(self, tmp_path):
        feeds_file = tmp_path / "feeds.txt"
        feeds_file.write_text(
            "# comment\nhttps://a.com/feed\n\nhttps://b.com/feed\n"
        )
        config = IntakeConfig(
            rss=RSSConfig(feeds_file=str(feeds_file))
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == ["https://a.com/feed", "https://b.com/feed"]

    def test_reads_opml(self, tmp_path):
        opml_file = tmp_path / "feeds.opml"
        opml_file.write_text(
            '<?xml version="1.0"?>'
            "<opml><body>"
            '<outline xmlUrl="https://a.com/feed" />'
            '<outline xmlUrl="https://b.com/feed" />'
            "</body></opml>"
        )
        config = IntakeConfig(
            rss=RSSConfig(opml_file=str(opml_file))
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == ["https://a.com/feed", "https://b.com/feed"]

    def test_missing_feeds_file(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds_file="/nonexistent/feeds.txt")
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == []

    def test_missing_opml_file(self):
        config = IntakeConfig(
            rss=RSSConfig(opml_file="/nonexistent/feeds.opml")
        )
        parser = RSSParser(config=config)
        urls = parser._resolve_feed_urls()
        assert urls == []


# ── Entry conversion ───────────────────────────────────────────────────

def _make_feed_entry(**overrides):
    """Create a mock feedparser entry."""
    # Use a recent timestamp so it passes the recency filter
    recent_time = time.gmtime(
        int((datetime.now(tz=UTC) - timedelta(days=1)).timestamp())
    )
    entry = {
        "title": "Test Article",
        "link": "https://example.com/article",
        "summary": "This is a test article about Python programming and stuff.",
        "author": "Test Author",
        "id": "guid-123",
        "published_parsed": recent_time,
        "tags": [{"term": "python"}, {"term": "ai"}],
    }
    entry.update(overrides)

    class FeedEntry(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    return FeedEntry(entry)


class TestEntryConversion:
    def _make_parser(self, min_word_count=0):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=min_word_count,
        )
        return RSSParser(config=config)

    def test_basic_conversion(self):
        parser = self._make_parser()
        entry = _make_feed_entry()
        item = parser._entry_to_item(entry, site_name="Example Blog")

        assert item is not None
        assert item.title == "Test Article"
        assert item.url == "https://example.com/article"
        assert item.author == "Test Author"
        assert item.site_name == "Example Blog"
        assert item.source == ContentSource.RSS
        assert item.content_type == ContentType.ARTICLE
        assert "python" in item.tags
        assert "ai" in item.tags
        assert item.source_id == "guid-123"

    def test_content_over_summary(self):
        parser = self._make_parser()
        entry = _make_feed_entry(
            content=[{"value": "<p>Full article content here with lots of words.</p>"}],
            summary="Short summary.",
        )
        item = parser._entry_to_item(entry)
        assert item is not None
        assert "Full article content" in item.body
        assert "Short summary" in item.excerpt

    def test_no_link_no_title_returns_none(self):
        parser = self._make_parser()
        entry = _make_feed_entry(title="", link="")
        item = parser._entry_to_item(entry)
        assert item is None

    def test_word_count(self):
        parser = self._make_parser()
        entry = _make_feed_entry(
            summary="one two three four five"
        )
        item = parser._entry_to_item(entry)
        assert item is not None
        assert item.word_count == 5

    def test_id_is_hash(self):
        parser = self._make_parser()
        entry = _make_feed_entry()
        item = parser._entry_to_item(entry)
        assert item is not None
        assert len(item.id) == 16  # sha256[:16]

    def test_stable_id(self):
        parser = self._make_parser()
        entry = _make_feed_entry()
        item1 = parser._entry_to_item(entry)
        item2 = parser._entry_to_item(entry)
        assert item1.id == item2.id

    def test_published_at_parsed(self):
        parser = self._make_parser()
        entry = _make_feed_entry()
        item = parser._entry_to_item(entry)
        assert item is not None
        assert item.published_at is not None
        assert item.published_at.tzinfo == UTC

    def test_no_date(self):
        parser = self._make_parser()
        entry = _make_feed_entry()
        del entry["published_parsed"]
        item = parser._entry_to_item(entry)
        assert item is not None
        assert item.published_at is None

    def test_feed_url_in_metadata(self):
        parser = self._make_parser()
        entry = _make_feed_entry()
        item = parser._entry_to_item(entry, feed_url="https://example.com/feed")
        assert item is not None
        assert item.metadata["feed_url"] == "https://example.com/feed"

    def test_author_falls_back_to_feed_author(self):
        parser = self._make_parser()
        entry = _make_feed_entry(author="")
        item = parser._entry_to_item(entry, feed_author="Feed Author")
        assert item is not None
        assert item.author == "Feed Author"

    def test_entry_author_takes_precedence(self):
        parser = self._make_parser()
        entry = _make_feed_entry(author="Entry Author")
        item = parser._entry_to_item(entry, feed_author="Feed Author")
        assert item is not None
        assert item.author == "Entry Author"

    def test_excerpt_from_first_paragraph(self):
        parser = self._make_parser()
        entry = _make_feed_entry(
            summary="",
            content=[{"value": "<p>First paragraph.</p><p>Second paragraph.</p>"}],
        )
        item = parser._entry_to_item(entry)
        assert item is not None
        assert "First paragraph" in item.excerpt


# ── Cross-feed dedup ──────────────────────────────────────────────────

class TestDedupByUrl:
    def test_deduplicates_same_url(self):
        url = "https://example.com/article"
        items = [
            ContentItem(
                id="a", url=url, source=ContentSource.RSS,
                word_count=100, body="short",
            ),
            ContentItem(
                id="b", url=url, source=ContentSource.RSS,
                word_count=500, body="longer version",
            ),
        ]
        result = RSSParser._dedup_by_url(items)
        assert len(result) == 1
        assert result[0].word_count == 500  # keeps the longer one

    def test_keeps_unique_urls(self):
        items = [
            ContentItem(id="a", url="https://example.com/a", source=ContentSource.RSS),
            ContentItem(id="b", url="https://example.com/b", source=ContentSource.RSS),
        ]
        result = RSSParser._dedup_by_url(items)
        assert len(result) == 2

    def test_normalizes_trailing_slash(self):
        items = [
            ContentItem(
                id="a", url="https://example.com/article/",
                source=ContentSource.RSS, word_count=100,
            ),
            ContentItem(
                id="b", url="https://example.com/article",
                source=ContentSource.RSS, word_count=200,
            ),
        ]
        result = RSSParser._dedup_by_url(items)
        assert len(result) == 1

    def test_preserves_items_without_url(self):
        items = [
            ContentItem(id="a", url="", source=ContentSource.RSS, title="No URL 1"),
            ContentItem(id="b", url="", source=ContentSource.RSS, title="No URL 2"),
        ]
        result = RSSParser._dedup_by_url(items)
        assert len(result) == 2


# ── Feed parsing ───────────────────────────────────────────────────────

class TestParseFeed:
    def test_parse_with_mock_feed(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Test Blog", "author": "Blog Owner"}
        mock_feed.entries = [_make_feed_entry()]

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 1
        assert items[0].site_name == "Test Blog"

    def test_since_filter(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Blog"}
        mock_feed.entries = [
            _make_feed_entry(published_parsed=time.gmtime(1707300000)),  # old
        ]

        future = datetime(2030, 1, 1, tzinfo=UTC)
        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=future)

        assert len(items) == 0

    def test_default_recency_filter(self):
        """When since=None, items older than max_age_days are filtered."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"], max_age_days=7),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        old_time = time.gmtime(
            int((datetime.now(tz=UTC) - timedelta(days=30)).timestamp())
        )
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Blog"}
        mock_feed.entries = [
            _make_feed_entry(published_parsed=old_time),
        ]

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=None)  # should default to 7 days

        assert len(items) == 0

    def test_word_count_filter(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=100,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Blog"}
        mock_feed.entries = [
            _make_feed_entry(summary="short"),  # only 1 word
        ]

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 0

    def test_bozo_feed_without_entries(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.bozo_exception = Exception("parse error")
        mock_feed.entries = []
        mock_feed.feed = {}

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 0

    def test_not_configured(self):
        config = IntakeConfig(rss=RSSConfig())
        parser = RSSParser(config=config)
        assert parser.is_configured is False

    def test_source_property(self):
        config = IntakeConfig(rss=RSSConfig(feeds=["https://a.com/feed"]))
        parser = RSSParser(config=config)
        assert parser.source == ContentSource.RSS

    def test_feed_author_used_when_entry_has_none(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Test Blog", "author": "Blog Owner"}
        mock_feed.entries = [_make_feed_entry(author="")]

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 1
        assert items[0].author == "Blog Owner"

    def test_bozo_feed_with_entries_still_returns_items(self):
        """Malformed feeds that still have entries should return items with a warning."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.bozo_exception = Exception("XML not well-formed")
        mock_feed.feed = {"title": "Broken Blog"}
        mock_feed.entries = [_make_feed_entry()]

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 1
        assert items[0].site_name == "Broken Blog"

    def test_feed_with_none_feed_meta(self):
        """Feed with no feed metadata should not crash."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = None
        mock_feed.entries = [_make_feed_entry()]

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 1
        assert items[0].site_name == ""

    def test_feed_with_none_entries(self):
        """Feed with entries=None should not crash."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Blog"}
        mock_feed.entries = None

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 0

    def test_fetch_feed_uses_timeout(self):
        """_fetch_feed should use configured timeout."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"], fetch_timeout=15),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<rss><channel></channel></rss>"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("distill.intake.parsers.rss.urlopen", return_value=mock_resp) as mock_urlopen:
            parser._fetch_feed("https://example.com/feed")
            mock_urlopen.assert_called_once()
            _, kwargs = mock_urlopen.call_args
            assert kwargs["timeout"] == 15

    def test_fetch_feed_falls_back_on_error(self):
        """If direct fetch fails, should fall back to feedparser."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        with (
            patch("distill.intake.parsers.rss.urlopen", side_effect=OSError("Connection refused")),
            patch("distill.intake.parsers.rss.feedparser.parse") as mock_fp,
        ):
            mock_fp.return_value = MagicMock(bozo=False, feed={}, entries=[])
            parser._fetch_feed("https://example.com/feed")
            mock_fp.assert_called_once_with("https://example.com/feed")

    def test_feed_exception_does_not_crash_parse(self):
        """A feed that raises an exception should be skipped, not crash."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://good.com/feed", "https://bad.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        good_feed = MagicMock()
        good_feed.bozo = False
        good_feed.feed = {"title": "Good Blog"}
        good_feed.entries = [_make_feed_entry()]

        def mock_fetch(url):
            if "bad.com" in url:
                raise OSError("Connection timed out")
            return good_feed

        with patch.object(parser, "_fetch_feed", side_effect=mock_fetch):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 1  # only good feed items

    def test_since_naive_datetime_gets_utc(self):
        """A naive datetime for since should be treated as UTC."""
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://example.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Blog"}
        mock_feed.entries = [_make_feed_entry()]

        naive_since = datetime(2020, 1, 1)  # no tzinfo
        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", return_value=mock_feed):
            items = parser.parse(since=naive_since)

        assert len(items) == 1

    def test_cross_feed_dedup(self):
        config = IntakeConfig(
            rss=RSSConfig(feeds=["https://a.com/feed", "https://b.com/feed"]),
            min_word_count=0,
        )
        parser = RSSParser(config=config)

        # Same article URL from two feeds
        entry = _make_feed_entry(link="https://shared.com/article")
        mock_feed_a = MagicMock()
        mock_feed_a.bozo = False
        mock_feed_a.feed = {"title": "Feed A"}
        mock_feed_a.entries = [entry]

        mock_feed_b = MagicMock()
        mock_feed_b.bozo = False
        mock_feed_b.feed = {"title": "Feed B"}
        mock_feed_b.entries = [entry]

        def mock_parse(url):
            return mock_feed_a if "a.com" in url else mock_feed_b

        with patch("distill.intake.parsers.rss.RSSParser._fetch_feed", side_effect=mock_parse):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=UTC))

        assert len(items) == 1


# ── Parser factory ─────────────────────────────────────────────────────

class TestParserFactory:
    def test_create_rss_parser(self):
        from distill.intake.parsers import create_parser

        config = IntakeConfig(rss=RSSConfig(feeds=["https://a.com/feed"]))
        parser = create_parser("rss", config=config)
        assert isinstance(parser, RSSParser)
        assert parser.is_configured is True

    def test_unknown_source(self):
        from distill.intake.parsers import create_parser

        config = IntakeConfig()
        with pytest.raises(ValueError):
            create_parser("unknown_source_xyz", config=config)

    def test_get_configured_parsers(self):
        from distill.intake.parsers import get_configured_parsers

        config = IntakeConfig(rss=RSSConfig(feeds=["https://a.com/feed"]))
        parsers = get_configured_parsers(config)
        assert len(parsers) >= 1
        assert any(p.source == ContentSource.RSS for p in parsers)

    def test_get_configured_parsers_none(self):
        from distill.intake.parsers import get_configured_parsers

        config = IntakeConfig(rss=RSSConfig())
        parsers = get_configured_parsers(config)
        rss_parsers = [p for p in parsers if p.source == ContentSource.RSS]
        assert len(rss_parsers) == 0
