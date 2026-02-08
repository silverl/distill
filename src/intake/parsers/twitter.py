"""Twitter/X data export and nitter RSS feed parser."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from calendar import timegm
from datetime import UTC, datetime, timedelta
from pathlib import Path

import feedparser
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 30

# Twitter date format: "Fri Feb 07 12:30:00 +0000 2026"
_TWITTER_DATE_FMT = "%a %b %d %H:%M:%S %z %Y"

# Pattern to strip JS variable assignment prefix
_JS_PREFIX_RE = re.compile(r"^window\.YTD\.\w+\.part0\s*=\s*")


class TwitterParser(ContentParser):
    """Parses Twitter/X data exports and nitter RSS feeds."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.TWITTER

    @property
    def is_configured(self) -> bool:
        return self._config.twitter.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_MAX_AGE_DAYS)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        items: list[ContentItem] = []

        if self._config.twitter.export_path:
            items.extend(self._parse_export(since))

        if self._config.twitter.nitter_feeds:
            items.extend(self._parse_nitter(since))

        items = self._dedup(items)

        max_items = self._config.max_items_per_source
        if len(items) > max_items:
            items = items[:max_items]

        return items

    # ── Export parsing ────────────────────────────────────────────────

    def _parse_export(self, since: datetime) -> list[ContentItem]:
        export_dir = Path(self._config.twitter.export_path).expanduser()
        data_dir = export_dir / "data"
        if not data_dir.is_dir():
            logger.warning("Twitter export data directory not found: %s", data_dir)
            return []

        items: list[ContentItem] = []

        # Likes
        likes_file = data_dir / "like.js"
        if likes_file.exists():
            items.extend(self._parse_likes(likes_file, since))

        # Bookmarks
        bookmarks_file = data_dir / "bookmarks.js"
        if bookmarks_file.exists():
            items.extend(self._parse_bookmarks(bookmarks_file, since))

        # Own tweets
        tweets_file = data_dir / "tweets.js"
        if tweets_file.exists():
            items.extend(self._parse_tweets(tweets_file, since))

        return items

    def _parse_likes(self, path: Path, since: datetime) -> list[ContentItem]:
        records = self._load_js_file(path)
        if records is None:
            return []

        items: list[ContentItem] = []
        for record in records:
            like_data = record.get("like", {})
            tweet_id = like_data.get("tweetId", "")
            if not tweet_id:
                continue

            full_text = like_data.get("fullText", "")
            url = f"https://twitter.com/i/status/{tweet_id}"
            item_id = hashlib.sha256(tweet_id.encode()).hexdigest()[:16]

            items.append(
                ContentItem(
                    id=item_id,
                    url=url,
                    title="",
                    body=full_text,
                    excerpt=full_text[:500] if full_text else "",
                    word_count=len(full_text.split()) if full_text else 0,
                    source=ContentSource.TWITTER,
                    source_id=tweet_id,
                    content_type=ContentType.POST,
                    is_starred=True,
                    metadata={"tweet_type": "like"},
                )
            )

        return items

    def _parse_bookmarks(self, path: Path, since: datetime) -> list[ContentItem]:
        records = self._load_js_file(path)
        if records is None:
            return []

        items: list[ContentItem] = []
        for record in records:
            bookmark_data = record.get("bookmark", {})
            tweet_id = bookmark_data.get("tweetId", "")
            if not tweet_id:
                continue

            full_text = bookmark_data.get("fullText", "")
            url = f"https://twitter.com/i/status/{tweet_id}"
            item_id = hashlib.sha256(tweet_id.encode()).hexdigest()[:16]

            items.append(
                ContentItem(
                    id=item_id,
                    url=url,
                    title="",
                    body=full_text,
                    excerpt=full_text[:500] if full_text else "",
                    word_count=len(full_text.split()) if full_text else 0,
                    source=ContentSource.TWITTER,
                    source_id=tweet_id,
                    content_type=ContentType.POST,
                    is_starred=True,
                    metadata={"tweet_type": "bookmark"},
                )
            )

        return items

    def _parse_tweets(self, path: Path, since: datetime) -> list[ContentItem]:
        records = self._load_js_file(path)
        if records is None:
            return []

        items: list[ContentItem] = []
        # Group by conversation_id for thread detection
        conversation_ids: dict[str, int] = {}
        for record in records:
            tweet_data = record.get("tweet", {})
            conv_id = tweet_data.get("conversation_id", "")
            if conv_id:
                conversation_ids[conv_id] = conversation_ids.get(conv_id, 0) + 1

        thread_conversations = {cid for cid, count in conversation_ids.items() if count > 1}

        for record in records:
            tweet_data = record.get("tweet", {})
            tweet_id = tweet_data.get("id", "")
            if not tweet_id:
                continue

            full_text = tweet_data.get("full_text", "")
            url = f"https://twitter.com/i/status/{tweet_id}"
            item_id = hashlib.sha256(tweet_id.encode()).hexdigest()[:16]

            # Parse date
            published_at = self._parse_twitter_date(tweet_data.get("created_at", ""))
            if published_at and published_at < since:
                continue

            # Extract hashtags
            entities = tweet_data.get("entities", {})
            hashtags = entities.get("hashtags", [])
            tags = [ht.get("text", "") for ht in hashtags if ht.get("text")]

            # Thread detection
            conv_id = tweet_data.get("conversation_id", "")
            is_thread = conv_id in thread_conversations
            content_type = ContentType.THREAD if is_thread else ContentType.POST

            items.append(
                ContentItem(
                    id=item_id,
                    url=url,
                    title="",
                    body=full_text,
                    excerpt=full_text[:500] if full_text else "",
                    word_count=len(full_text.split()) if full_text else 0,
                    source=ContentSource.TWITTER,
                    source_id=tweet_id,
                    content_type=content_type,
                    tags=tags,
                    published_at=published_at,
                    is_starred=False,
                    metadata={
                        "tweet_type": "tweet",
                        "conversation_id": conv_id,
                    },
                )
            )

        return items

    @staticmethod
    def _load_js_file(path: Path) -> list[dict] | None:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("Failed to read Twitter export file: %s", path)
            return None

        text = _JS_PREFIX_RE.sub("", text).strip()
        if not text:
            return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Twitter export file: %s", path)
            return None

        if not isinstance(data, list):
            return None

        return data

    @staticmethod
    def _parse_twitter_date(date_str: str) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, _TWITTER_DATE_FMT)
        except ValueError:
            logger.debug("Failed to parse Twitter date: %s", date_str)
            return None

    # ── Nitter RSS parsing ───────────────────────────────────────────

    def _parse_nitter(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []
        for feed_url in self._config.twitter.nitter_feeds:
            try:
                feed_items = self._parse_nitter_feed(feed_url, since)
                items.extend(feed_items)
            except Exception:
                logger.warning("Failed to parse nitter feed: %s", feed_url, exc_info=True)
        return items

    def _parse_nitter_feed(self, url: str, since: datetime) -> list[ContentItem]:
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("Nitter feed error for %s: %s", url, feed.bozo_exception)
            return []

        items: list[ContentItem] = []
        for entry in feed.entries:
            link = entry.get("link", "")
            title = entry.get("title", "")
            summary = entry.get("summary", "")

            id_source = link or title
            if not id_source:
                continue

            item_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

            published_at = self._parse_feed_date(entry)
            if published_at and published_at < since:
                continue

            body = summary
            word_count = len(body.split()) if body else 0

            items.append(
                ContentItem(
                    id=item_id,
                    url=link,
                    title=title,
                    body=body,
                    excerpt=body[:500] if body else "",
                    word_count=word_count,
                    source=ContentSource.TWITTER,
                    source_id=entry.get("id", link),
                    content_type=ContentType.POST,
                    published_at=published_at,
                    metadata={"feed_url": url},
                )
            )

        return items

    @staticmethod
    def _parse_feed_date(entry: feedparser.FeedParserDict) -> datetime | None:
        for field in ("published_parsed", "updated_parsed"):
            time_struct = entry.get(field)
            if time_struct:
                try:
                    return datetime.fromtimestamp(timegm(time_struct), tz=UTC)
                except (ValueError, OverflowError):
                    continue
        return None

    # ── Deduplication ────────────────────────────────────────────────

    @staticmethod
    def _dedup(items: list[ContentItem]) -> list[ContentItem]:
        seen: dict[str, ContentItem] = {}
        for item in items:
            key = item.source_id or item.url or item.id
            if key not in seen or item.word_count > seen[key].word_count:
                seen[key] = item
        return list(seen.values())
