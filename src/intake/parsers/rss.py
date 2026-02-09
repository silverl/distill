"""RSS/Atom feed parser."""

from __future__ import annotations

import hashlib
import html as html_module
import logging
import re
import xml.etree.ElementTree as ET
from calendar import timegm
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import feedparser
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

# Default to last 7 days when no `since` is provided and no state exists
_DEFAULT_MAX_AGE_DAYS = 7


class RSSParser(ContentParser):
    """Parses RSS and Atom feeds into ContentItem objects."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.RSS

    @property
    def is_configured(self) -> bool:
        return self._config.rss.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        """Fetch and parse all configured RSS feeds.

        Args:
            since: Only return entries published after this time.
                   When None, defaults to last 7 days.

        Returns:
            Deduplicated list of ContentItem objects from all feeds.
        """
        feed_urls = self._resolve_feed_urls()
        if not feed_urls:
            logger.warning("No RSS feed URLs configured")
            return []

        # Default recency filter: last 7 days
        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=self._config.rss.max_age_days)
        elif since.tzinfo is None:
            # Ensure timezone-aware for comparison with feed dates
            since = since.replace(tzinfo=UTC)

        items: list[ContentItem] = []
        for url in feed_urls:
            try:
                feed_items = self._parse_feed(url, since=since)
                items.extend(feed_items)
            except Exception:
                logger.warning("Failed to parse feed: %s", url, exc_info=True)

        # Cross-feed dedup: same article URL from multiple feeds
        items = self._dedup_by_url(items)

        logger.info("Parsed %d items from %d RSS feeds", len(items), len(feed_urls))
        return items

    @staticmethod
    def _dedup_by_url(items: list[ContentItem]) -> list[ContentItem]:
        """Deduplicate items by URL, keeping the version with the most content."""
        by_url: dict[str, ContentItem] = {}
        no_url: list[ContentItem] = []

        for item in items:
            if not item.url:
                no_url.append(item)
                continue

            # Normalize URL for comparison (strip fragments, trailing slashes)
            normalized = _normalize_url(item.url)
            existing = by_url.get(normalized)
            if existing is None:
                by_url[normalized] = item
            elif item.word_count > existing.word_count:
                # Keep the version with more content
                by_url[normalized] = item

        return list(by_url.values()) + no_url

    def _resolve_feed_urls(self) -> list[str]:
        """Collect feed URLs from all configured sources."""
        urls: list[str] = list(self._config.rss.feeds)

        if self._config.rss.feeds_file:
            urls.extend(self._read_feeds_file(self._config.rss.feeds_file))

        if self._config.rss.opml_file:
            urls.extend(self._read_opml(self._config.rss.opml_file))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            normalized = url.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)

        return unique

    def _fetch_feed(self, url: str) -> feedparser.FeedParserDict:
        """Fetch and parse a feed URL with timeout."""
        timeout = self._config.rss.fetch_timeout
        try:
            req = Request(url, headers={"User-Agent": "distill-rss/1.0"})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                data = resp.read()
            return feedparser.parse(data)
        except Exception:
            # Fall back to feedparser's built-in fetching (no timeout)
            logger.debug("Direct fetch failed for %s, falling back to feedparser", url)
            return feedparser.parse(url)

    def _parse_feed(self, url: str, *, since: datetime | None = None) -> list[ContentItem]:
        """Parse a single RSS/Atom feed URL."""
        feed = self._fetch_feed(url)

        if feed.bozo and not feed.entries:
            logger.warning("Feed error for %s: %s", url, feed.bozo_exception)
            return []

        if feed.bozo:
            logger.warning(
                "Feed %s has errors but returned %d entries: %s",
                url,
                len(feed.entries),
                feed.bozo_exception,
            )

        feed_meta = feed.feed if feed.feed else {}
        site_name = feed_meta.get("title", "") if isinstance(feed_meta, dict) else ""
        feed_author = feed_meta.get("author", "") if isinstance(feed_meta, dict) else ""
        items: list[ContentItem] = []
        max_items = self._config.rss.max_items_per_feed
        entries = feed.entries if feed.entries else []

        for entry in entries[:max_items]:
            item = self._entry_to_item(
                entry,
                site_name=site_name,
                feed_url=url,
                feed_author=feed_author,
            )
            if item is None:
                continue
            if since and item.published_at and item.published_at < since:
                continue
            if item.word_count < self._config.min_word_count:
                continue
            items.append(item)

        return items

    def _entry_to_item(
        self,
        entry: feedparser.FeedParserDict,
        *,
        site_name: str = "",
        feed_url: str = "",
        feed_author: str = "",
    ) -> ContentItem | None:
        """Convert a feedparser entry to a ContentItem."""
        link = entry.get("link", "")
        title = entry.get("title", "")

        if not link and not title:
            return None

        # Extract body from content or summary
        body = self._extract_body(entry)
        excerpt = self._make_excerpt(entry, body)

        # Parse published date
        published_at = self._parse_date(entry)

        # Generate stable ID from URL or title
        id_source = link or title
        item_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

        # Author: entry-level > feed-level > empty
        author = entry.get("author", "") or feed_author

        tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]

        word_count = len(body.split()) if body else 0

        return ContentItem(
            id=item_id,
            url=link,
            title=title,
            body=body,
            excerpt=excerpt,
            word_count=word_count,
            author=author,
            site_name=site_name,
            source=ContentSource.RSS,
            source_id=entry.get("id", link),
            content_type=ContentType.ARTICLE,
            tags=tags,
            published_at=published_at,
            metadata={"feed_url": feed_url},
        )

    @staticmethod
    def _extract_body(entry: feedparser.FeedParserDict) -> str:
        """Extract the best available body text from a feed entry."""
        # Prefer full content over summary
        content_list = entry.get("content", [])
        if content_list:
            # Pick the longest content block (often HTML)
            best = max(content_list, key=lambda c: len(c.get("value", "")))
            return _strip_html(best.get("value", ""))

        summary = entry.get("summary", "")
        if summary:
            return _strip_html(summary)

        return ""

    @staticmethod
    def _make_excerpt(entry: feedparser.FeedParserDict, body: str) -> str:
        """Build a clean excerpt — first meaningful paragraph."""
        # Use summary if it differs from body
        summary = entry.get("summary", "")
        if summary:
            clean_summary = _strip_html(summary)
            if clean_summary != body:
                return clean_summary[:500]

        if not body:
            return ""

        # Extract first paragraph
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        if paragraphs:
            return paragraphs[0][:500]

        return body[:500]

    @staticmethod
    def _parse_date(entry: feedparser.FeedParserDict) -> datetime | None:
        """Parse the published date from a feed entry."""
        for field in ("published_parsed", "updated_parsed"):
            time_struct = entry.get(field)
            if time_struct:
                try:
                    return datetime.fromtimestamp(timegm(time_struct), tz=UTC)
                except (ValueError, OverflowError):
                    continue
        return None

    @staticmethod
    def _read_feeds_file(path: str) -> list[str]:
        """Read feed URLs from a newline-delimited text file."""
        feeds_path = Path(path).expanduser()
        if not feeds_path.exists():
            logger.warning("Feeds file not found: %s", path)
            return []

        lines = feeds_path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    @staticmethod
    def _read_opml(path: str) -> list[str]:
        """Extract feed URLs from an OPML file."""
        opml_path = Path(path).expanduser()
        if not opml_path.exists():
            logger.warning("OPML file not found: %s", path)
            return []

        try:
            tree = ET.parse(opml_path)  # noqa: S314
        except ET.ParseError:
            logger.warning("Failed to parse OPML file: %s", path, exc_info=True)
            return []

        urls: list[str] = []
        for outline in tree.iter("outline"):
            xml_url = outline.get("xmlUrl", "")
            if xml_url:
                urls.append(xml_url)

        return urls


# ── HTML cleaning ─────────────────────────────────────────────────────


class _HTMLTextExtractor(HTMLParser):
    """Proper HTML-to-text converter using stdlib html.parser."""

    # Tags that should insert whitespace when stripped
    _BLOCK_TAGS = frozenset(
        {
            "p",
            "div",
            "br",
            "hr",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "pre",
            "tr",
            "td",
            "th",
            "dt",
            "dd",
            "figcaption",
            "article",
            "section",
            "header",
            "footer",
            "nav",
            "aside",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0  # depth inside <script>/<style>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth == 0:
            char = html_module.unescape(f"&{name};")
            self._parts.append(char)

    def handle_charref(self, name: str) -> None:
        if self._skip_depth == 0:
            char = html_module.unescape(f"&#{name};")
            self._parts.append(char)

    def get_text(self) -> str:
        text = "".join(self._parts)
        # Collapse runs of whitespace within lines
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Clean up leading/trailing whitespace per line
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(lines).strip()


def _strip_html(html: str) -> str:
    """Convert HTML to clean plain text."""
    if not html:
        return ""

    # Fast path: no HTML tags at all
    if "<" not in html:
        return html_module.unescape(html).strip()

    try:
        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        return extractor.get_text()
    except Exception:
        # Fallback: regex-based stripping if parser fails
        text = re.sub(r"<[^>]+>", " ", html)
        text = html_module.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def _normalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""
    parsed = urlparse(url)
    # Strip fragment and trailing slash
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"
