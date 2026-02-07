"""Full-text extraction for content items with truncated bodies.

When RSS feeds only provide excerpts or summaries, this module fetches
the original article URL and extracts the full text plus metadata
(author, title) using ``trafilatura``.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from distill.intake.models import ContentItem
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_USER_AGENT = "Distill/1.0 (+https://github.com/distill; content pipeline)"

# Delay between consecutive HTTP requests (seconds)
_REQUEST_DELAY = 0.5

# Try to import trafilatura at module level so it can be mocked in tests.
try:
    import trafilatura as _trafilatura
except ImportError:
    _trafilatura: Any = None  # type: ignore[no-redef]


def _trafilatura_available() -> bool:
    """Check whether trafilatura is installed."""
    return _trafilatura is not None


class FullTextResult(BaseModel):
    """Result of a full-text extraction attempt."""

    body: str = ""
    author: str = ""
    title: str = ""
    word_count: int = 0
    success: bool = False
    error: str = ""


def fetch_full_text(url: str, timeout: int = 15) -> FullTextResult:
    """Fetch a URL and extract its article text and metadata.

    Uses ``urllib.request`` for HTTP fetching and ``trafilatura`` for
    content extraction. Returns a :class:`FullTextResult` that is always
    safe to inspect (``success=False`` on any error).

    Args:
        url: The article URL to fetch.
        timeout: HTTP request timeout in seconds.

    Returns:
        Extraction result with body, author, title, and word count.
    """
    if not url:
        return FullTextResult(error="Empty URL")

    if not _trafilatura_available():
        return FullTextResult(error="trafilatura is not installed")

    try:
        request = Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            html = response.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return FullTextResult(error=f"Fetch failed: {exc}")
    except Exception as exc:
        logger.debug("Unexpected error fetching %s: %s", url, exc)
        return FullTextResult(error=f"Fetch failed: {exc}")

    try:
        extracted = _trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            output_format="txt",
        )
    except Exception as exc:
        logger.debug("Extraction failed for %s: %s", url, exc)
        return FullTextResult(error=f"Extraction failed: {exc}")

    if not extracted:
        return FullTextResult(error="No content extracted")

    # Extract metadata separately
    metadata = _trafilatura.extract_metadata(html)
    author = ""
    title = ""
    if metadata:
        author = metadata.author or ""
        title = metadata.title or ""

    word_count = len(extracted.split())
    return FullTextResult(
        body=extracted,
        author=author,
        title=title,
        word_count=word_count,
        success=True,
    )


def enrich_items(
    items: list[ContentItem],
    min_word_threshold: int = 100,
    max_concurrent: int = 10,
) -> list[ContentItem]:
    """Enrich content items that have short bodies by fetching full text.

    Items whose ``word_count`` is already >= *min_word_threshold* are
    returned unchanged. For the rest, the original URL is fetched and
    the body (and optionally author) are populated from the extracted
    article.

    A small delay is inserted between HTTP requests to respect rate
    limits.

    Args:
        items: Content items to potentially enrich.
        min_word_threshold: Minimum word count below which full-text
            fetching is attempted.
        max_concurrent: Maximum number of items to enrich in a single
            call (acts as a budget cap, not parallelism).

    Returns:
        The same list of items, with short-body items enriched in place.
    """
    if not _trafilatura_available():
        logger.warning("trafilatura is not installed — skipping full-text enrichment")
        return items

    enriched_count = 0
    for item in items:
        if enriched_count >= max_concurrent:
            logger.info("Reached max enrichment budget (%d); stopping", max_concurrent)
            break

        if item.word_count >= min_word_threshold:
            continue

        if not item.url:
            continue

        # Rate limiting: pause between requests
        if enriched_count > 0:
            time.sleep(_REQUEST_DELAY)

        result = fetch_full_text(item.url)
        if not result.success:
            logger.debug("Could not enrich '%s': %s", item.title or item.url, result.error)
            continue

        item.body = result.body
        item.word_count = result.word_count

        # Populate author from page metadata when item has none
        if not item.author and result.author:
            item.author = result.author

        # Populate title from page metadata when item has none
        if not item.title and result.title:
            item.title = result.title

        enriched_count += 1
        logger.debug("Enriched '%s' — %d words", item.title or item.url, result.word_count)

    if enriched_count:
        logger.info("Enriched %d/%d items with full text", enriched_count, len(items))

    return items
