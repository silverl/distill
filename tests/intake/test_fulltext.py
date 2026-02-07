"""Tests for full-text extraction and enrichment."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from distill.intake.fulltext import (
    _REQUEST_DELAY,
    FullTextResult,
    enrich_items,
    fetch_full_text,
)
from distill.intake.models import ContentItem, ContentSource, ContentType

# ── Helpers ──────────────────────────────────────────────────────────


def _make_item(
    title: str = "Test Article",
    url: str = "https://example.com/test",
    body: str = "",
    word_count: int = 0,
    author: str = "",
) -> ContentItem:
    return ContentItem(
        id=f"test-{hash(title + url) % 10000}",
        url=url,
        title=title,
        body=body,
        word_count=word_count,
        author=author,
        source=ContentSource.RSS,
        content_type=ContentType.ARTICLE,
        published_at=datetime(2026, 2, 7, 10, 0),
    )


_SAMPLE_HTML = """
<html>
<head><title>Great Article</title></head>
<body>
<article>
<h1>Great Article</h1>
<p>This is the full text of a great article about testing software.
It has multiple paragraphs and enough words to be meaningful content
that would normally be truncated in an RSS feed excerpt.</p>
<p>Second paragraph with additional details and information that
makes this article worth reading in its entirety.</p>
</article>
</body>
</html>
"""

_EXTRACTED_TEXT = (
    "This is the full text of a great article about testing software. "
    "It has multiple paragraphs and enough words to be meaningful content "
    "that would normally be truncated in an RSS feed excerpt. "
    "Second paragraph with additional details and information that "
    "makes this article worth reading in its entirety."
)


def _mock_urlopen(html: str = _SAMPLE_HTML):
    """Create a mock urlopen context manager returning HTML bytes."""
    mock_response = MagicMock()
    mock_response.read.return_value = html.encode("utf-8")
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


# ── FullTextResult model tests ───────────────────────────────────────


class TestFullTextResult:
    def test_defaults(self) -> None:
        result = FullTextResult()
        assert result.body == ""
        assert result.author == ""
        assert result.title == ""
        assert result.word_count == 0
        assert result.success is False
        assert result.error == ""

    def test_success_result(self) -> None:
        result = FullTextResult(
            body="Article text here",
            author="Jane Doe",
            title="My Article",
            word_count=3,
            success=True,
        )
        assert result.success is True
        assert result.body == "Article text here"
        assert result.author == "Jane Doe"
        assert result.title == "My Article"

    def test_error_result(self) -> None:
        result = FullTextResult(error="Connection refused", success=False)
        assert result.success is False
        assert result.error == "Connection refused"

    def test_serialization(self) -> None:
        result = FullTextResult(body="text", word_count=1, success=True)
        data = result.model_dump()
        restored = FullTextResult.model_validate(data)
        assert restored.body == "text"
        assert restored.success is True


# ── fetch_full_text tests ────────────────────────────────────────────


class TestFetchFullText:
    def test_empty_url(self) -> None:
        result = fetch_full_text("")
        assert result.success is False
        assert "Empty URL" in result.error

    @patch("distill.intake.fulltext._trafilatura_available", return_value=False)
    def test_trafilatura_not_installed(self, mock_avail: MagicMock) -> None:
        result = fetch_full_text("https://example.com")
        assert result.success is False
        assert "trafilatura" in result.error

    @patch("distill.intake.fulltext.urlopen")
    @patch("distill.intake.fulltext._trafilatura")
    def test_successful_extraction(self, mock_traf: MagicMock, mock_urlopen_fn: MagicMock) -> None:
        mock_urlopen_fn.return_value = _mock_urlopen()
        mock_traf.extract.return_value = _EXTRACTED_TEXT
        mock_metadata = MagicMock()
        mock_metadata.author = "Alice Smith"
        mock_metadata.title = "Great Article"
        mock_traf.extract_metadata.return_value = mock_metadata

        result = fetch_full_text("https://example.com/article")

        assert result.success is True
        assert result.body == _EXTRACTED_TEXT
        assert result.author == "Alice Smith"
        assert result.title == "Great Article"
        assert result.word_count > 0

    @patch("distill.intake.fulltext.urlopen")
    def test_network_error(self, mock_urlopen_fn: MagicMock) -> None:
        from urllib.error import URLError

        mock_urlopen_fn.side_effect = URLError("Connection refused")
        result = fetch_full_text("https://example.com/fail")
        assert result.success is False
        assert "Fetch failed" in result.error

    @patch("distill.intake.fulltext.urlopen")
    def test_timeout_error(self, mock_urlopen_fn: MagicMock) -> None:
        mock_urlopen_fn.side_effect = TimeoutError("Request timed out")
        result = fetch_full_text("https://example.com/slow")
        assert result.success is False
        assert "Fetch failed" in result.error

    @patch("distill.intake.fulltext.urlopen")
    @patch("distill.intake.fulltext._trafilatura")
    def test_extraction_returns_none(
        self, mock_traf: MagicMock, mock_urlopen_fn: MagicMock
    ) -> None:
        mock_urlopen_fn.return_value = _mock_urlopen()
        mock_traf.extract.return_value = None

        result = fetch_full_text("https://example.com/empty")
        assert result.success is False
        assert "No content extracted" in result.error

    @patch("distill.intake.fulltext.urlopen")
    @patch("distill.intake.fulltext._trafilatura")
    def test_extraction_exception(self, mock_traf: MagicMock, mock_urlopen_fn: MagicMock) -> None:
        mock_urlopen_fn.return_value = _mock_urlopen()
        mock_traf.extract.side_effect = RuntimeError("parse error")

        result = fetch_full_text("https://example.com/broken")
        assert result.success is False
        assert "Extraction failed" in result.error

    @patch("distill.intake.fulltext.urlopen")
    @patch("distill.intake.fulltext._trafilatura")
    def test_metadata_none(self, mock_traf: MagicMock, mock_urlopen_fn: MagicMock) -> None:
        mock_urlopen_fn.return_value = _mock_urlopen()
        mock_traf.extract.return_value = "Some article text"
        mock_traf.extract_metadata.return_value = None

        result = fetch_full_text("https://example.com/no-meta")
        assert result.success is True
        assert result.body == "Some article text"
        assert result.author == ""
        assert result.title == ""

    @patch("distill.intake.fulltext.urlopen")
    def test_user_agent_header(self, mock_urlopen_fn: MagicMock) -> None:
        """Verify that requests include a User-Agent header."""
        mock_urlopen_fn.return_value = _mock_urlopen()

        with patch("distill.intake.fulltext._trafilatura") as mock_traf:
            mock_traf.extract.return_value = "text"
            mock_traf.extract_metadata.return_value = None
            fetch_full_text("https://example.com/ua")

        # Inspect the Request object passed to urlopen
        call_args = mock_urlopen_fn.call_args
        request_obj = call_args[0][0]
        assert request_obj.get_header("User-agent") is not None


# ── enrich_items tests ───────────────────────────────────────────────


class TestEnrichItems:
    @patch("distill.intake.fulltext._trafilatura_available", return_value=False)
    def test_skips_when_trafilatura_unavailable(self, mock_avail: MagicMock) -> None:
        items = [_make_item(word_count=10)]
        result = enrich_items(items)
        assert len(result) == 1
        assert result[0].word_count == 10  # unchanged

    def test_skips_items_with_sufficient_word_count(self) -> None:
        items = [
            _make_item(word_count=200, body="x " * 200),
            _make_item(word_count=150, body="y " * 150),
        ]
        with patch("distill.intake.fulltext.fetch_full_text") as mock_fetch:
            result = enrich_items(items, min_word_threshold=100)

        mock_fetch.assert_not_called()
        assert len(result) == 2

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_enriches_short_items(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        mock_fetch.return_value = FullTextResult(
            body="Full article text with many words",
            author="Extracted Author",
            title="Extracted Title",
            word_count=6,
            success=True,
        )

        item = _make_item(word_count=10, url="https://example.com/short")
        result = enrich_items([item], min_word_threshold=100)

        assert result[0].body == "Full article text with many words"
        assert result[0].word_count == 6
        mock_fetch.assert_called_once_with("https://example.com/short")

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_populates_author_when_missing(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = FullTextResult(
            body="content",
            author="Page Author",
            word_count=1,
            success=True,
        )

        item = _make_item(word_count=10, author="")
        enrich_items([item], min_word_threshold=100)

        assert item.author == "Page Author"

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_preserves_existing_author(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        mock_fetch.return_value = FullTextResult(
            body="content",
            author="Page Author",
            word_count=1,
            success=True,
        )

        item = _make_item(word_count=10, author="Original Author")
        enrich_items([item], min_word_threshold=100)

        assert item.author == "Original Author"

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_skips_items_without_url(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        item = _make_item(word_count=10, url="")
        enrich_items([item], min_word_threshold=100)
        mock_fetch.assert_not_called()

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_handles_fetch_failure_gracefully(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = FullTextResult(error="Connection refused", success=False)

        item = _make_item(word_count=10, body="short")
        result = enrich_items([item], min_word_threshold=100)

        assert result[0].body == "short"  # unchanged
        assert result[0].word_count == 10  # unchanged

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_respects_max_concurrent_budget(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = FullTextResult(
            body="full text",
            word_count=2,
            success=True,
        )

        items = [
            _make_item(title=f"Item {i}", url=f"https://example.com/{i}", word_count=5)
            for i in range(20)
        ]
        enrich_items(items, min_word_threshold=100, max_concurrent=3)

        assert mock_fetch.call_count == 3

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_rate_limiting_delays(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        """Verify that a delay is inserted between consecutive requests."""
        mock_fetch.return_value = FullTextResult(body="text", word_count=1, success=True)

        items = [
            _make_item(title=f"Item {i}", url=f"https://example.com/{i}", word_count=5)
            for i in range(3)
        ]
        enrich_items(items, min_word_threshold=100)

        # First request has no delay; subsequent requests each have one
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(_REQUEST_DELAY)

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_mixed_items_only_enriches_short_ones(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = FullTextResult(
            body="enriched text",
            word_count=2,
            success=True,
        )

        items = [
            _make_item(title="Long", word_count=500, body="x " * 500),
            _make_item(title="Short", word_count=10, url="https://example.com/short"),
            _make_item(title="Also Long", word_count=300, body="y " * 300),
        ]
        enrich_items(items, min_word_threshold=100)

        assert mock_fetch.call_count == 1
        # Only the short item was enriched
        assert items[0].body == "x " * 500
        assert items[1].body == "enriched text"
        assert items[2].body == "y " * 300

    @patch("distill.intake.fulltext.time.sleep")
    @patch("distill.intake.fulltext.fetch_full_text")
    def test_populates_title_when_missing(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = FullTextResult(
            body="content",
            title="Extracted Title",
            word_count=1,
            success=True,
        )

        item = _make_item(title="", word_count=10)
        enrich_items([item], min_word_threshold=100)

        assert item.title == "Extracted Title"
