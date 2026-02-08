"""Tests for Substack newsletter parser."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.config import IntakeConfig, SubstackIntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.substack import SubstackParser


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_feed_entry(**overrides):
    """Create a mock feedparser entry."""
    recent_time = time.gmtime(
        int((datetime.now(tz=timezone.utc) - timedelta(days=1)).timestamp())
    )
    entry = {
        "title": "Test Newsletter Post",
        "link": "https://example.substack.com/p/test-post",
        "summary": "<p>This is a test newsletter about AI programming and stuff.</p>",
        "author": "Newsletter Author",
        "id": "substack-guid-123",
        "published_parsed": recent_time,
        "tags": [{"term": "ai"}, {"term": "programming"}],
    }
    entry.update(overrides)

    class FeedEntry(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    return FeedEntry(entry)


def _make_mock_feed(entries=None, title="Test Newsletter", bozo=False):
    """Create a mock feedparser feed."""
    feed = MagicMock()
    feed.bozo = bozo
    feed.feed = {"title": title}
    feed.entries = entries if entries is not None else [_make_feed_entry()]
    return feed


def _make_parser(blog_urls=None, max_items_per_source=50):
    """Create a SubstackParser with the given config."""
    config = IntakeConfig(
        substack=SubstackIntakeConfig(
            blog_urls=blog_urls or ["https://example.substack.com"],
        ),
        max_items_per_source=max_items_per_source,
    )
    return SubstackParser(config=config)


# ── Feed URL conversion ─────────────────────────────────────────────────


class TestFeedUrlConversion:
    def test_blog_url_to_feed_url(self):
        """Blog URL gets /feed appended."""
        parser = _make_parser(blog_urls=["https://example.substack.com"])
        mock_feed = _make_mock_feed()

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed) as mock_parse:
            parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
            mock_parse.assert_called_once_with("https://example.substack.com/feed")

    def test_blog_url_strips_trailing_slash(self):
        """Trailing slash on blog URL is stripped before appending /feed."""
        parser = _make_parser(blog_urls=["https://example.substack.com/"])
        mock_feed = _make_mock_feed()

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed) as mock_parse:
            parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
            mock_parse.assert_called_once_with("https://example.substack.com/feed")


# ── is_configured ─────────────────────────────────────────────────────


class TestIsConfigured:
    def test_configured_when_blog_urls_set(self):
        parser = _make_parser(blog_urls=["https://example.substack.com"])
        assert parser.is_configured is True

    def test_not_configured_when_empty(self):
        config = IntakeConfig(substack=SubstackIntakeConfig(blog_urls=[]))
        parser = SubstackParser(config=config)
        assert parser.is_configured is False

    def test_not_configured_default(self):
        config = IntakeConfig()
        parser = SubstackParser(config=config)
        assert parser.is_configured is False


# ── source property ──────────────────────────────────────────────────


class TestSourceProperty:
    def test_source_is_substack(self):
        parser = _make_parser()
        assert parser.source == ContentSource.SUBSTACK


# ── Feed parsing ─────────────────────────────────────────────────────


class TestFeedParsing:
    def test_basic_parsing(self):
        parser = _make_parser()
        entry = _make_feed_entry()
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].title == "Test Newsletter Post"
        assert items[0].url == "https://example.substack.com/p/test-post"
        assert items[0].source == ContentSource.SUBSTACK

    def test_html_stripping_in_body(self):
        parser = _make_parser()
        entry = _make_feed_entry(
            summary="<p>Hello <b>world</b> with <a href='url'>link</a></p>",
        )
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "<p>" not in items[0].body
        assert "<b>" not in items[0].body
        assert "Hello" in items[0].body
        assert "world" in items[0].body

    def test_content_preferred_over_summary(self):
        parser = _make_parser()
        entry = _make_feed_entry(
            content=[{"value": "<p>Full newsletter content here with lots of detail.</p>"}],
            summary="Short summary only.",
        )
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "Full newsletter content" in items[0].body

    def test_site_name_from_feed_title(self):
        parser = _make_parser()
        mock_feed = _make_mock_feed(title="Amazing Newsletter")

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].site_name == "Amazing Newsletter"


# ── Date filtering ────────────────────────────────────────────────────


class TestDateFiltering:
    def test_since_filters_old_entries(self):
        parser = _make_parser()
        old_time = time.gmtime(
            int((datetime.now(tz=timezone.utc) - timedelta(days=30)).timestamp())
        )
        entry = _make_feed_entry(published_parsed=old_time)
        mock_feed = _make_mock_feed(entries=[entry])

        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=future)

        assert len(items) == 0

    def test_default_7_day_window(self):
        """When since is None, entries older than 7 days are filtered."""
        parser = _make_parser()
        old_time = time.gmtime(
            int((datetime.now(tz=timezone.utc) - timedelta(days=30)).timestamp())
        )
        entry = _make_feed_entry(published_parsed=old_time)
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=None)

        assert len(items) == 0

    def test_recent_entries_pass_default_filter(self):
        """Recent entries (within 7 days) pass the default filter."""
        parser = _make_parser()
        recent_time = time.gmtime(
            int((datetime.now(tz=timezone.utc) - timedelta(days=1)).timestamp())
        )
        entry = _make_feed_entry(published_parsed=recent_time)
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=None)

        assert len(items) == 1


# ── Edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_feed(self):
        parser = _make_parser()
        mock_feed = _make_mock_feed(entries=[])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items == []

    def test_no_blog_urls_configured(self):
        config = IntakeConfig(substack=SubstackIntakeConfig(blog_urls=[]))
        parser = SubstackParser(config=config)
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_bozo_feed_without_entries(self):
        parser = _make_parser()
        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.bozo_exception = Exception("parse error")
        mock_feed.entries = []
        mock_feed.feed = {}

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items == []

    def test_feed_parse_exception_handled(self):
        parser = _make_parser()

        with patch("distill.intake.parsers.substack.feedparser.parse", side_effect=Exception("network error")):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items == []


# ── Deduplication ─────────────────────────────────────────────────────


class TestDeduplication:
    def test_dedup_across_feeds(self):
        parser = _make_parser(
            blog_urls=["https://a.substack.com", "https://b.substack.com"]
        )
        # Same article URL in both feeds
        entry = _make_feed_entry(link="https://shared.substack.com/p/same-post")
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1

    def test_different_urls_kept(self):
        parser = _make_parser()
        entries = [
            _make_feed_entry(
                link="https://example.substack.com/p/post-1",
                title="Post 1",
            ),
            _make_feed_entry(
                link="https://example.substack.com/p/post-2",
                title="Post 2",
            ),
        ]
        mock_feed = _make_mock_feed(entries=entries)

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 2


# ── max_items_per_source ──────────────────────────────────────────────


class TestMaxItems:
    def test_limits_to_max_items(self):
        parser = _make_parser(max_items_per_source=2)
        entries = [
            _make_feed_entry(link=f"https://example.substack.com/p/post-{i}", title=f"Post {i}")
            for i in range(5)
        ]
        mock_feed = _make_mock_feed(entries=entries)

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 2


# ── Content type ──────────────────────────────────────────────────────


class TestContentType:
    def test_content_type_is_newsletter(self):
        parser = _make_parser()
        mock_feed = _make_mock_feed()

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].content_type == ContentType.NEWSLETTER


# ── Author extraction ────────────────────────────────────────────────


class TestAuthorExtraction:
    def test_author_from_entry(self):
        parser = _make_parser()
        entry = _make_feed_entry(author="Jane Doe")
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].author == "Jane Doe"

    def test_empty_author(self):
        parser = _make_parser()
        entry = _make_feed_entry(author="")
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].author == ""


# ── Tag extraction ────────────────────────────────────────────────────


class TestTagExtraction:
    def test_tags_from_entry(self):
        parser = _make_parser()
        entry = _make_feed_entry(tags=[{"term": "ai"}, {"term": "ml"}, {"term": "python"}])
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].tags == ["ai", "ml", "python"]

    def test_no_tags(self):
        parser = _make_parser()
        entry = _make_feed_entry()
        del entry["tags"]
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].tags == []

    def test_empty_term_filtered(self):
        parser = _make_parser()
        entry = _make_feed_entry(tags=[{"term": "ai"}, {"term": ""}, {"other": "x"}])
        mock_feed = _make_mock_feed(entries=[entry])

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items[0].tags == ["ai"]


# ── Stable ID generation ─────────────────────────────────────────────


class TestStableId:
    def test_id_is_sha256_prefix(self):
        parser = _make_parser()
        mock_feed = _make_mock_feed()

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert len(items[0].id) == 16
        link = "https://example.substack.com/p/test-post"
        expected_id = hashlib.sha256(link.encode()).hexdigest()[:16]
        assert items[0].id == expected_id

    def test_stable_across_parses(self):
        parser = _make_parser()
        mock_feed = _make_mock_feed()

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items1 = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        with patch("distill.intake.parsers.substack.feedparser.parse", return_value=mock_feed):
            items2 = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))

        assert items1[0].id == items2[0].id
