"""Tests for Twitter/X parser."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.config import IntakeConfig, TwitterIntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.twitter import TwitterParser


# ── Helpers ──────────────────────────────────────────────────────────


def _make_config(
    export_path: str = "",
    nitter_feeds: list[str] | None = None,
    max_items_per_source: int = 50,
) -> IntakeConfig:
    return IntakeConfig(
        twitter=TwitterIntakeConfig(
            export_path=export_path,
            nitter_feeds=nitter_feeds or [],
        ),
        max_items_per_source=max_items_per_source,
    )


def _write_js(path: Path, prefix: str, data: list[dict]) -> None:
    """Write a Twitter export JS file."""
    path.write_text(f"{prefix}{json.dumps(data)}", encoding="utf-8")


SAMPLE_LIKE = {"like": {"tweetId": "123456", "fullText": "Great tweet about AI"}}
SAMPLE_BOOKMARK = {"bookmark": {"tweetId": "789012", "fullText": "Bookmarked content here"}}
SAMPLE_TWEET = {
    "tweet": {
        "id": "111222",
        "full_text": "Hello world from my timeline",
        "created_at": "Fri Feb 07 12:30:00 +0000 2026",
        "entities": {"hashtags": [{"text": "AI"}, {"text": "ML"}]},
    }
}
SAMPLE_TWEET_THREAD_A = {
    "tweet": {
        "id": "333001",
        "full_text": "Thread start",
        "created_at": "Fri Feb 07 10:00:00 +0000 2026",
        "conversation_id": "333001",
        "entities": {"hashtags": []},
    }
}
SAMPLE_TWEET_THREAD_B = {
    "tweet": {
        "id": "333002",
        "full_text": "Thread reply",
        "created_at": "Fri Feb 07 10:05:00 +0000 2026",
        "conversation_id": "333001",
        "entities": {"hashtags": []},
    }
}


# ── is_configured ────────────────────────────────────────────────────


class TestIsConfigured:
    def test_configured_with_export_path(self, tmp_path: Path):
        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        assert parser.is_configured is True

    def test_configured_with_nitter_feeds(self):
        config = _make_config(nitter_feeds=["https://nitter.net/user/rss"])
        parser = TwitterParser(config=config)
        assert parser.is_configured is True

    def test_not_configured_with_neither(self):
        config = _make_config()
        parser = TwitterParser(config=config)
        assert parser.is_configured is False


# ── source property ──────────────────────────────────────────────────


class TestSource:
    def test_source_returns_twitter(self):
        config = _make_config()
        parser = TwitterParser(config=config)
        assert parser.source == ContentSource.TWITTER


# ── JS prefix stripping ─────────────────────────────────────────────


class TestJsPrefixStripping:
    def test_strips_like_prefix(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "like.js",
            "window.YTD.like.part0 = ",
            [SAMPLE_LIKE],
        )
        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert len(items) >= 1

    def test_strips_tweets_prefix(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "tweets.js",
            "window.YTD.tweets.part0 = ",
            [SAMPLE_TWEET],
        )
        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert len(items) >= 1

    def test_strips_bookmarks_prefix(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "bookmarks.js",
            "window.YTD.bookmarks.part0 = ",
            [SAMPLE_BOOKMARK],
        )
        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert len(items) >= 1


# ── Like parsing ─────────────────────────────────────────────────────


class TestParseLikes:
    def test_parses_likes(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [SAMPLE_LIKE])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 1
        assert items[0].body == "Great tweet about AI"
        assert items[0].is_starred is True
        assert items[0].source == ContentSource.TWITTER

    def test_likes_url_from_tweet_id(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [SAMPLE_LIKE])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].url == "https://twitter.com/i/status/123456"

    def test_likes_empty_fulltext(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        like_no_text = {"like": {"tweetId": "999", "fullText": ""}}
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [like_no_text])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 1
        assert items[0].body == ""
        assert items[0].word_count == 0


# ── Tweet parsing ────────────────────────────────────────────────────


class TestParseTweets:
    def test_parses_tweets_full_text(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 1
        assert items[0].body == "Hello world from my timeline"

    def test_tweets_not_starred(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].is_starred is False

    def test_tweets_url_from_id(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].url == "https://twitter.com/i/status/111222"


# ── Hashtag extraction ───────────────────────────────────────────────


class TestHashtagExtraction:
    def test_extracts_hashtags_as_tags(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert "AI" in items[0].tags
        assert "ML" in items[0].tags

    def test_no_hashtags(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tweet_no_tags = {
            "tweet": {
                "id": "555",
                "full_text": "No hashtags here",
                "created_at": "Fri Feb 07 12:30:00 +0000 2026",
                "entities": {"hashtags": []},
            }
        }
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [tweet_no_tags])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].tags == []


# ── Date parsing ─────────────────────────────────────────────────────


class TestDateParsing:
    def test_parses_twitter_date_format(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].published_at is not None
        assert items[0].published_at.year == 2026
        assert items[0].published_at.month == 2
        assert items[0].published_at.day == 7

    def test_invalid_date_returns_none(self):
        result = TwitterParser._parse_twitter_date("not a date")
        assert result is None

    def test_empty_date_returns_none(self):
        result = TwitterParser._parse_twitter_date("")
        assert result is None


# ── Thread detection ─────────────────────────────────────────────────


class TestThreadDetection:
    def test_detects_thread_via_conversation_id(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "tweets.js",
            "window.YTD.tweets.part0 = ",
            [SAMPLE_TWEET_THREAD_A, SAMPLE_TWEET_THREAD_B],
        )

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 2
        assert all(item.content_type == ContentType.THREAD for item in items)

    def test_single_tweet_not_thread(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].content_type == ContentType.POST


# ── Since-date filtering ─────────────────────────────────────────────


class TestSinceDateFiltering:
    def test_filters_old_tweets(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        old_tweet = {
            "tweet": {
                "id": "old1",
                "full_text": "Old tweet",
                "created_at": "Mon Jan 01 00:00:00 +0000 2024",
                "entities": {"hashtags": []},
            }
        }
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [old_tweet])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        items = parser.parse(since=since)

        assert len(items) == 0

    def test_keeps_recent_tweets(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        items = parser.parse(since=since)

        assert len(items) == 1

    def test_naive_since_treated_as_utc(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "tweets.js", "window.YTD.tweets.part0 = ", [SAMPLE_TWEET])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        since = datetime(2025, 1, 1)  # naive
        items = parser.parse(since=since)

        assert len(items) == 1


# ── Bookmark parsing ─────────────────────────────────────────────────


class TestParseBookmarks:
    def test_parses_bookmarks(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "bookmarks.js",
            "window.YTD.bookmarks.part0 = ",
            [SAMPLE_BOOKMARK],
        )

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 1
        assert items[0].body == "Bookmarked content here"
        assert items[0].is_starred is True

    def test_bookmarks_url(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "bookmarks.js",
            "window.YTD.bookmarks.part0 = ",
            [SAMPLE_BOOKMARK],
        )

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].url == "https://twitter.com/i/status/789012"


# ── Nitter RSS parsing ──────────────────────────────────────────────


class TestNitterParsing:
    @patch("distill.intake.parsers.twitter.feedparser.parse")
    def test_parses_nitter_feed(self, mock_parse: MagicMock):
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "link": "https://nitter.net/user/status/42",
                "title": "A nitter post",
                "summary": "Some content from nitter RSS",
                "published_parsed": time.gmtime(
                    datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
                ),
            }
        ]
        mock_parse.return_value = mock_feed

        config = _make_config(nitter_feeds=["https://nitter.net/user/rss"])
        parser = TwitterParser(config=config)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].source == ContentSource.TWITTER
        assert items[0].title == "A nitter post"
        assert items[0].body == "Some content from nitter RSS"

    @patch("distill.intake.parsers.twitter.feedparser.parse")
    def test_nitter_filters_by_since(self, mock_parse: MagicMock):
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "link": "https://nitter.net/user/status/old",
                "title": "Old post",
                "summary": "Old content",
                "published_parsed": time.gmtime(
                    datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
                ),
            }
        ]
        mock_parse.return_value = mock_feed

        config = _make_config(nitter_feeds=["https://nitter.net/user/rss"])
        parser = TwitterParser(config=config)
        items = parser.parse(since=datetime(2025, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 0

    @patch("distill.intake.parsers.twitter.feedparser.parse")
    def test_nitter_bozo_no_entries(self, mock_parse: MagicMock):
        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.entries = []
        mock_feed.bozo_exception = Exception("bad feed")
        mock_parse.return_value = mock_feed

        config = _make_config(nitter_feeds=["https://nitter.net/bad/rss"])
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 0

    @patch("distill.intake.parsers.twitter.feedparser.parse")
    def test_nitter_metadata_has_feed_url(self, mock_parse: MagicMock):
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "link": "https://nitter.net/user/status/99",
                "title": "Post",
                "summary": "Content",
                "published_parsed": time.gmtime(
                    datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
                ),
            }
        ]
        mock_parse.return_value = mock_feed

        config = _make_config(nitter_feeds=["https://nitter.net/user/rss"])
        parser = TwitterParser(config=config)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert items[0].metadata["feed_url"] == "https://nitter.net/user/rss"


# ── Deduplication ────────────────────────────────────────────────────


class TestDeduplication:
    def test_dedup_across_files(self, tmp_path: Path):
        """Same tweet ID in likes and bookmarks should be deduped."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        like = {"like": {"tweetId": "shared123", "fullText": "Short"}}
        bookmark = {"bookmark": {"tweetId": "shared123", "fullText": "Longer version of the text"}}

        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [like])
        _write_js(data_dir / "bookmarks.js", "window.YTD.bookmarks.part0 = ", [bookmark])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 1
        # Should keep the one with more content
        assert items[0].body == "Longer version of the text"

    def test_dedup_different_ids_kept(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        like1 = {"like": {"tweetId": "aaa", "fullText": "First"}}
        like2 = {"like": {"tweetId": "bbb", "fullText": "Second"}}

        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [like1, like2])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 2


# ── Missing / malformed files ────────────────────────────────────────


class TestMissingFiles:
    def test_missing_data_dir(self, tmp_path: Path):
        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert items == []

    def test_missing_individual_files(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # No JS files exist
        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert items == []

    def test_empty_js_file(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "like.js").write_text("", encoding="utf-8")

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert items == []

    def test_malformed_json(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "like.js").write_text(
            "window.YTD.like.part0 = {not valid json",
            encoding="utf-8",
        )

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert items == []

    def test_js_file_with_object_not_list(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "like.js").write_text(
            'window.YTD.like.part0 = {"not": "a list"}',
            encoding="utf-8",
        )

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()
        assert items == []


# ── max_items_per_source limiting ────────────────────────────────────


class TestMaxItemsLimit:
    def test_limits_total_items(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        likes = [
            {"like": {"tweetId": f"id_{i}", "fullText": f"Tweet {i}"}} for i in range(10)
        ]
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", likes)

        config = _make_config(export_path=str(tmp_path), max_items_per_source=3)
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert len(items) == 3


# ── Combined export + nitter ─────────────────────────────────────────


class TestCombined:
    @patch("distill.intake.parsers.twitter.feedparser.parse")
    def test_combines_export_and_nitter(self, mock_parse: MagicMock, tmp_path: Path):
        # Export
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [SAMPLE_LIKE])

        # Nitter
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "link": "https://nitter.net/user/status/nitter1",
                "title": "Nitter post",
                "summary": "Nitter content",
                "published_parsed": time.gmtime(
                    datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
                ),
            }
        ]
        mock_parse.return_value = mock_feed

        config = _make_config(
            export_path=str(tmp_path),
            nitter_feeds=["https://nitter.net/user/rss"],
        )
        parser = TwitterParser(config=config)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        # Should have items from both sources
        assert len(items) == 2
        sources = {item.metadata.get("tweet_type", item.metadata.get("feed_url")) for item in items}
        assert "like" in sources


# ── Stable ID generation ─────────────────────────────────────────────


class TestStableIds:
    def test_id_is_sha256_prefix(self, tmp_path: Path):
        import hashlib

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [SAMPLE_LIKE])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        expected_id = hashlib.sha256("123456".encode()).hexdigest()[:16]
        assert items[0].id == expected_id

    def test_id_deterministic(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [SAMPLE_LIKE])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items1 = parser.parse()
        items2 = parser.parse()

        assert items1[0].id == items2[0].id


# ── Content type assignment ──────────────────────────────────────────


class TestContentType:
    def test_likes_are_post_type(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(data_dir / "like.js", "window.YTD.like.part0 = ", [SAMPLE_LIKE])

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].content_type == ContentType.POST

    def test_bookmarks_are_post_type(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_js(
            data_dir / "bookmarks.js",
            "window.YTD.bookmarks.part0 = ",
            [SAMPLE_BOOKMARK],
        )

        config = _make_config(export_path=str(tmp_path))
        parser = TwitterParser(config=config)
        items = parser.parse()

        assert items[0].content_type == ContentType.POST
