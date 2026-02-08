"""Substack newsletter parser via RSS feeds."""

from __future__ import annotations

import hashlib
import logging
from calendar import timegm
from datetime import UTC, datetime, timedelta

import feedparser
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser
from distill.intake.parsers.rss import _strip_html

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 7


class SubstackParser(ContentParser):
    """Parses Substack newsletters via their RSS feeds."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.SUBSTACK

    @property
    def is_configured(self) -> bool:
        return self._config.substack.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        """Fetch and parse all configured Substack feeds.

        Args:
            since: Only return entries published after this time.
                   When None, defaults to last 7 days.

        Returns:
            Deduplicated list of ContentItem objects from all feeds.
        """
        blog_urls = self._config.substack.blog_urls
        if not blog_urls:
            logger.warning("No Substack blog URLs configured")
            return []

        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_MAX_AGE_DAYS)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        items: list[ContentItem] = []
        seen_urls: set[str] = set()

        for blog_url in blog_urls:
            feed_url = f"{blog_url.rstrip('/')}/feed"
            try:
                feed_items = self._parse_feed(feed_url, since=since, seen_urls=seen_urls)
                items.extend(feed_items)
            except Exception:
                logger.warning("Failed to parse Substack feed: %s", feed_url, exc_info=True)

        # Limit to max_items_per_source
        items = items[: self._config.max_items_per_source]

        logger.info("Parsed %d items from %d Substack feeds", len(items), len(blog_urls))
        return items

    def _parse_feed(
        self,
        feed_url: str,
        *,
        since: datetime,
        seen_urls: set[str],
    ) -> list[ContentItem]:
        """Parse a single Substack RSS feed."""
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            logger.warning("Feed error for %s: %s", feed_url, getattr(feed, "bozo_exception", ""))
            return []

        site_name = feed.feed.get("title", "")
        items: list[ContentItem] = []

        for entry in feed.entries:
            link = entry.get("link", "")

            # Deduplicate across feeds
            if link and link in seen_urls:
                continue
            if link:
                seen_urls.add(link)

            title = entry.get("title", "")
            if not link and not title:
                continue

            body = self._extract_body(entry)
            author = entry.get("author", "")
            published_at = self._parse_date(entry)

            # Filter by since
            if published_at and published_at < since:
                continue

            tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]

            item_id = (
                hashlib.sha256(link.encode()).hexdigest()[:16]
                if link
                else hashlib.sha256(title.encode()).hexdigest()[:16]
            )
            word_count = len(body.split()) if body else 0

            items.append(
                ContentItem(
                    id=item_id,
                    url=link,
                    title=title,
                    body=body,
                    excerpt=body[:500] if body else "",
                    word_count=word_count,
                    author=author,
                    site_name=site_name,
                    source=ContentSource.SUBSTACK,
                    source_id=entry.get("id", link),
                    content_type=ContentType.NEWSLETTER,
                    tags=tags,
                    published_at=published_at,
                    metadata={"feed_url": feed_url},
                )
            )

        return items

    @staticmethod
    def _extract_body(entry: feedparser.FeedParserDict) -> str:
        """Extract the best available body text from a feed entry."""
        content_list = entry.get("content", [])
        if content_list:
            best = max(content_list, key=lambda c: len(c.get("value", "")))
            return _strip_html(best.get("value", ""))

        summary = entry.get("summary", "")
        if summary:
            return _strip_html(summary)

        return ""

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
