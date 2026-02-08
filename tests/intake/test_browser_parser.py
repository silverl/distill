"""Tests for the browser history parser."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.config import BrowserIntakeConfig, IntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.browser import (
    BrowserParser,
    _CHROME_EPOCH,
    _SAFARI_EPOCH,
    chrome_timestamp_to_datetime,
    safari_timestamp_to_datetime,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def config() -> IntakeConfig:
    return IntakeConfig(
        browser=BrowserIntakeConfig(
            browsers=["chrome"],
            domain_blocklist=["google.com", "localhost"],
            domain_allowlist=[],
        ),
    )


@pytest.fixture()
def parser(config: IntakeConfig) -> BrowserParser:
    return BrowserParser(config=config)


# ── Timestamp conversion ─────────────────────────────────────────────


class TestChromeTimestamp:
    def test_epoch_returns_1601(self) -> None:
        result = chrome_timestamp_to_datetime(0)
        assert result == datetime(1601, 1, 1, tzinfo=timezone.utc)

    def test_known_value(self) -> None:
        # 2023-01-01 00:00:00 UTC in Chrome time
        # Seconds from 1601 to 2023 = (2023-1601) years worth of seconds
        dt = datetime(2023, 1, 1, tzinfo=timezone.utc)
        chrome_ts = int((dt - _CHROME_EPOCH).total_seconds() * 1_000_000)
        result = chrome_timestamp_to_datetime(chrome_ts)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 1

    def test_returns_utc(self) -> None:
        result = chrome_timestamp_to_datetime(1_000_000)
        assert result.tzinfo == timezone.utc


class TestSafariTimestamp:
    def test_epoch_returns_2001(self) -> None:
        result = safari_timestamp_to_datetime(0)
        assert result == datetime(2001, 1, 1, tzinfo=timezone.utc)

    def test_known_value(self) -> None:
        # 2023-01-01 in Safari time
        dt = datetime(2023, 1, 1, tzinfo=timezone.utc)
        safari_ts = (dt - _SAFARI_EPOCH).total_seconds()
        result = safari_timestamp_to_datetime(safari_ts)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 1

    def test_returns_utc(self) -> None:
        result = safari_timestamp_to_datetime(100.0)
        assert result.tzinfo == timezone.utc


# ── Source and is_configured ──────────────────────────────────────────


class TestSourceProperty:
    def test_source_is_browser(self, parser: BrowserParser) -> None:
        assert parser.source == ContentSource.BROWSER

    def test_source_value(self, parser: BrowserParser) -> None:
        assert parser.source.value == "browser"


class TestIsConfigured:
    def test_default_is_configured(self, parser: BrowserParser) -> None:
        # BrowserIntakeConfig.is_configured always returns True
        assert parser.is_configured is True

    def test_delegates_to_config(self) -> None:
        config = IntakeConfig()
        p = BrowserParser(config=config)
        assert p.is_configured == config.browser.is_configured


# ── Domain filtering ─────────────────────────────────────────────────


class TestDomainFiltering:
    def test_blocklist_rejects_blocked_domain(self, parser: BrowserParser) -> None:
        assert parser._passes_domain_filter("https://www.google.com/search") is False

    def test_blocklist_rejects_localhost(self, parser: BrowserParser) -> None:
        assert parser._passes_domain_filter("http://localhost:3000/app") is False

    def test_blocklist_allows_unblocked_domain(self, parser: BrowserParser) -> None:
        assert parser._passes_domain_filter("https://example.com/article") is True

    def test_allowlist_overrides_blocklist(self) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(
                domain_allowlist=["example.com"],
                domain_blocklist=["google.com"],
            ),
        )
        p = BrowserParser(config=config)
        # Only allowlisted domains pass
        assert p._passes_domain_filter("https://example.com/page") is True
        assert p._passes_domain_filter("https://other.com/page") is False
        # Blocklist is ignored when allowlist is set
        assert p._passes_domain_filter("https://google.com/search") is False

    def test_no_filters_allows_everything(self) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(
                domain_allowlist=[],
                domain_blocklist=[],
            ),
        )
        p = BrowserParser(config=config)
        assert p._passes_domain_filter("https://anything.com") is True

    def test_invalid_url_rejected(self, parser: BrowserParser) -> None:
        # urlparse handles most strings, but empty netloc means no domain
        assert parser._passes_domain_filter("not-a-url") is True  # no netloc, no block match


# ── Deduplication ─────────────────────────────────────────────────────


class TestDeduplication:
    def test_dedup_by_url(self) -> None:
        items = [
            ContentItem(
                id="a1",
                url="https://example.com/page",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            ),
            ContentItem(
                id="a2",
                url="https://example.com/page",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            ),
        ]
        result = BrowserParser._dedup_by_url(items)
        assert len(result) == 1
        assert result[0].id == "a1"

    def test_different_urls_kept(self) -> None:
        items = [
            ContentItem(
                id="a1",
                url="https://example.com/page1",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            ),
            ContentItem(
                id="a2",
                url="https://example.com/page2",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            ),
        ]
        result = BrowserParser._dedup_by_url(items)
        assert len(result) == 2


# ── Chrome parsing ────────────────────────────────────────────────────


class TestChromeParser:
    @patch("distill.intake.parsers.browser._CHROME_HISTORY_PATH")
    def test_missing_db_returns_empty(
        self, mock_path: MagicMock, parser: BrowserParser
    ) -> None:
        mock_path.exists.return_value = False
        result = parser._parse_chrome(
            datetime.now(tz=timezone.utc) - timedelta(days=7)
        )
        assert result == []

    @patch("distill.intake.parsers.browser.BrowserParser._query_db")
    @patch("distill.intake.parsers.browser._CHROME_HISTORY_PATH")
    def test_parses_chrome_rows(
        self,
        mock_path: MagicMock,
        mock_query: MagicMock,
        parser: BrowserParser,
    ) -> None:
        mock_path.exists.return_value = True

        now = datetime.now(tz=timezone.utc)
        chrome_ts = int((now - _CHROME_EPOCH).total_seconds() * 1_000_000)

        mock_query.return_value = [
            ("https://example.com/article", "Example Article", 3, chrome_ts),
        ]

        since = now - timedelta(days=7)
        result = parser._parse_chrome(since)

        assert len(result) == 1
        assert result[0].url == "https://example.com/article"
        assert result[0].title == "Example Article"
        assert result[0].source == ContentSource.BROWSER
        assert result[0].content_type == ContentType.WEBPAGE
        assert result[0].metadata["browser"] == "chrome"
        assert result[0].metadata["visit_count"] == 3

    @patch("distill.intake.parsers.browser.BrowserParser._query_db")
    @patch("distill.intake.parsers.browser._CHROME_HISTORY_PATH")
    def test_filters_blocked_domains(
        self,
        mock_path: MagicMock,
        mock_query: MagicMock,
        parser: BrowserParser,
    ) -> None:
        mock_path.exists.return_value = True
        now = datetime.now(tz=timezone.utc)
        chrome_ts = int((now - _CHROME_EPOCH).total_seconds() * 1_000_000)

        mock_query.return_value = [
            ("https://www.google.com/search?q=test", "Google Search", 1, chrome_ts),
            ("https://example.com/good", "Good Article", 1, chrome_ts),
        ]

        result = parser._parse_chrome(now - timedelta(days=7))
        assert len(result) == 1
        assert result[0].url == "https://example.com/good"

    @patch("distill.intake.parsers.browser.BrowserParser._query_db")
    @patch("distill.intake.parsers.browser._CHROME_HISTORY_PATH")
    def test_generates_stable_ids(
        self,
        mock_path: MagicMock,
        mock_query: MagicMock,
        parser: BrowserParser,
    ) -> None:
        mock_path.exists.return_value = True
        now = datetime.now(tz=timezone.utc)
        chrome_ts = int((now - _CHROME_EPOCH).total_seconds() * 1_000_000)

        mock_query.return_value = [
            ("https://example.com/page", "Page", 1, chrome_ts),
        ]

        result1 = parser._parse_chrome(now - timedelta(days=7))
        result2 = parser._parse_chrome(now - timedelta(days=7))

        assert result1[0].id == result2[0].id
        assert len(result1[0].id) == 16


# ── Safari parsing ────────────────────────────────────────────────────


class TestSafariParser:
    @patch("distill.intake.parsers.browser._SAFARI_HISTORY_PATH")
    def test_missing_db_returns_empty(
        self, mock_path: MagicMock, parser: BrowserParser
    ) -> None:
        mock_path.exists.return_value = False
        config = IntakeConfig(
            browser=BrowserIntakeConfig(
                browsers=["safari"],
                domain_blocklist=[],
            ),
        )
        p = BrowserParser(config=config)
        result = p._parse_safari(
            datetime.now(tz=timezone.utc) - timedelta(days=7)
        )
        assert result == []

    @patch("distill.intake.parsers.browser.BrowserParser._query_db")
    @patch("distill.intake.parsers.browser._SAFARI_HISTORY_PATH")
    def test_parses_safari_rows(
        self,
        mock_path: MagicMock,
        mock_query: MagicMock,
    ) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(
                browsers=["safari"],
                domain_blocklist=[],
            ),
        )
        p = BrowserParser(config=config)
        mock_path.exists.return_value = True

        now = datetime.now(tz=timezone.utc)
        safari_ts = (now - _SAFARI_EPOCH).total_seconds()

        mock_query.return_value = [
            ("https://example.com/safari-article", "Safari Article", safari_ts),
        ]

        since = now - timedelta(days=7)
        result = p._parse_safari(since)

        assert len(result) == 1
        assert result[0].url == "https://example.com/safari-article"
        assert result[0].title == "Safari Article"
        assert result[0].source == ContentSource.BROWSER
        assert result[0].content_type == ContentType.WEBPAGE
        assert result[0].metadata["browser"] == "safari"

    @patch("distill.intake.parsers.browser.BrowserParser._query_db")
    @patch("distill.intake.parsers.browser._SAFARI_HISTORY_PATH")
    def test_safari_since_filtering(
        self,
        mock_path: MagicMock,
        mock_query: MagicMock,
    ) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(
                browsers=["safari"],
                domain_blocklist=[],
            ),
        )
        p = BrowserParser(config=config)
        mock_path.exists.return_value = True

        now = datetime.now(tz=timezone.utc)
        recent_ts = (now - timedelta(days=1) - _SAFARI_EPOCH).total_seconds()
        old_ts = (now - timedelta(days=30) - _SAFARI_EPOCH).total_seconds()

        mock_query.return_value = [
            ("https://example.com/recent", "Recent", recent_ts),
            ("https://example.com/old", "Old", old_ts),
        ]

        since = now - timedelta(days=7)
        result = p._parse_safari(since)

        assert len(result) == 1
        assert result[0].url == "https://example.com/recent"


# ── Full parse() method ──────────────────────────────────────────────


class TestParseMethod:
    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_parse_calls_chrome(
        self, mock_chrome: MagicMock, parser: BrowserParser
    ) -> None:
        mock_chrome.return_value = []
        parser.parse()
        mock_chrome.assert_called_once()

    @patch("distill.intake.parsers.browser.BrowserParser._parse_safari")
    def test_parse_calls_safari(self, mock_safari: MagicMock) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(browsers=["safari"]),
        )
        p = BrowserParser(config=config)
        mock_safari.return_value = []
        p.parse()
        mock_safari.assert_called_once()

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    @patch("distill.intake.parsers.browser.BrowserParser._parse_safari")
    def test_parse_both_browsers(
        self, mock_safari: MagicMock, mock_chrome: MagicMock
    ) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(browsers=["chrome", "safari"]),
        )
        p = BrowserParser(config=config)
        mock_chrome.return_value = []
        mock_safari.return_value = []
        p.parse()
        mock_chrome.assert_called_once()
        mock_safari.assert_called_once()

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_default_since_is_7_days(
        self, mock_chrome: MagicMock, parser: BrowserParser
    ) -> None:
        mock_chrome.return_value = []
        parser.parse(since=None)
        call_args = mock_chrome.call_args[0]
        since_arg = call_args[0]
        expected = datetime.now(tz=timezone.utc) - timedelta(days=7)
        # Within 5 seconds tolerance
        assert abs((since_arg - expected).total_seconds()) < 5

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_naive_since_gets_utc(
        self, mock_chrome: MagicMock, parser: BrowserParser
    ) -> None:
        mock_chrome.return_value = []
        naive_dt = datetime(2024, 1, 1)
        parser.parse(since=naive_dt)
        call_args = mock_chrome.call_args[0]
        since_arg = call_args[0]
        assert since_arg.tzinfo == timezone.utc

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_max_items_per_source_limit(
        self, mock_chrome: MagicMock, parser: BrowserParser
    ) -> None:
        # Create more items than max_items_per_source (default 50)
        items = [
            ContentItem(
                id=f"item-{i}",
                url=f"https://example.com/page-{i}",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            )
            for i in range(100)
        ]
        mock_chrome.return_value = items
        result = parser.parse()
        assert len(result) == parser._config.max_items_per_source

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_empty_history(
        self, mock_chrome: MagicMock, parser: BrowserParser
    ) -> None:
        mock_chrome.return_value = []
        result = parser.parse()
        assert result == []

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_unsupported_browser_skipped(
        self, mock_chrome: MagicMock
    ) -> None:
        config = IntakeConfig(
            browser=BrowserIntakeConfig(browsers=["firefox", "chrome"]),
        )
        p = BrowserParser(config=config)
        mock_chrome.return_value = []
        result = p.parse()
        # Should not crash, just skip firefox
        assert result == []
        mock_chrome.assert_called_once()

    @patch("distill.intake.parsers.browser.BrowserParser._parse_chrome")
    def test_dedup_across_parse(
        self, mock_chrome: MagicMock, parser: BrowserParser
    ) -> None:
        items = [
            ContentItem(
                id="a1",
                url="https://example.com/same",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            ),
            ContentItem(
                id="a2",
                url="https://example.com/same",
                source=ContentSource.BROWSER,
                content_type=ContentType.WEBPAGE,
            ),
        ]
        mock_chrome.return_value = items
        result = parser.parse()
        assert len(result) == 1


# ── _query_db ─────────────────────────────────────────────────────────


class TestQueryDb:
    @patch("distill.intake.parsers.browser.sqlite3.connect")
    @patch("distill.intake.parsers.browser.shutil.copy2")
    @patch("distill.intake.parsers.browser.tempfile.NamedTemporaryFile")
    def test_copies_db_before_query(
        self,
        mock_tmpfile: MagicMock,
        mock_copy: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        tmp = MagicMock()
        tmp.name = "/tmp/test.db"
        tmp.__enter__ = MagicMock(return_value=tmp)
        tmp.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = tmp

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("https://example.com", "Test", 1, 100)]
        mock_conn.execute.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        from pathlib import Path

        result = BrowserParser._query_db(
            Path("/fake/History"), "SELECT * FROM urls", ()
        )

        mock_copy.assert_called_once_with(Path("/fake/History"), "/tmp/test.db")
        mock_connect.assert_called_once_with("/tmp/test.db")
        assert len(result) == 1

    @patch("distill.intake.parsers.browser.shutil.copy2")
    def test_handles_copy_failure(self, mock_copy: MagicMock) -> None:
        mock_copy.side_effect = OSError("Permission denied")

        from pathlib import Path

        result = BrowserParser._query_db(
            Path("/fake/History"), "SELECT * FROM urls", ()
        )
        assert result == []

    @patch("distill.intake.parsers.browser.sqlite3.connect")
    @patch("distill.intake.parsers.browser.shutil.copy2")
    @patch("distill.intake.parsers.browser.tempfile.NamedTemporaryFile")
    def test_handles_sqlite_error(
        self,
        mock_tmpfile: MagicMock,
        mock_copy: MagicMock,
        mock_connect: MagicMock,
    ) -> None:
        tmp = MagicMock()
        tmp.name = "/tmp/test.db"
        tmp.__enter__ = MagicMock(return_value=tmp)
        tmp.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = tmp

        mock_connect.side_effect = sqlite3.Error("database is locked")

        from pathlib import Path

        result = BrowserParser._query_db(
            Path("/fake/History"), "SELECT * FROM urls", ()
        )
        assert result == []
