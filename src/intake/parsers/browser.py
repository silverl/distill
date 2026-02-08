"""Browser history parser — reads Chrome and Safari local SQLite databases."""

from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 7

# Chrome timestamps are microseconds since 1601-01-01 (Windows FILETIME epoch)
_CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)

# Safari timestamps are seconds since 2001-01-01 (Mac absolute time)
_SAFARI_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)

_CHROME_HISTORY_PATH = Path(
    "~/Library/Application Support/Google/Chrome/Default/History"
).expanduser()

_SAFARI_HISTORY_PATH = Path("~/Library/Safari/History.db").expanduser()

_CHROME_SQL = (
    "SELECT url, title, visit_count, last_visit_time "
    "FROM urls WHERE last_visit_time > ? ORDER BY last_visit_time DESC"
)

_SAFARI_SQL = (
    "SELECT h.url, v.title, v.visit_time "
    "FROM history_items h "
    "JOIN history_visits v ON h.id = v.history_item "
    "ORDER BY v.visit_time DESC"
)


def chrome_timestamp_to_datetime(timestamp: int) -> datetime:
    """Convert a Chrome microsecond-since-1601 timestamp to a UTC datetime."""
    return _CHROME_EPOCH + timedelta(microseconds=timestamp)


def safari_timestamp_to_datetime(timestamp: float) -> datetime:
    """Convert a Safari seconds-since-2001 timestamp to a UTC datetime."""
    return _SAFARI_EPOCH + timedelta(seconds=timestamp)


class BrowserParser(ContentParser):
    """Parses browser history from local SQLite databases."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.BROWSER

    @property
    def is_configured(self) -> bool:
        return self._config.browser.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_MAX_AGE_DAYS)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        items: list[ContentItem] = []
        browsers = self._config.browser.browsers

        for browser in browsers:
            browser_lower = browser.lower()
            try:
                if browser_lower == "chrome":
                    items.extend(self._parse_chrome(since))
                elif browser_lower == "safari":
                    items.extend(self._parse_safari(since))
                else:
                    logger.warning("Unsupported browser: %s", browser)
            except Exception:
                logger.warning("Failed to parse %s history", browser, exc_info=True)

        # Deduplicate by URL
        items = self._dedup_by_url(items)

        # Apply max_items_per_source limit
        max_items = self._config.max_items_per_source
        if len(items) > max_items:
            items = items[:max_items]

        return items

    def _parse_chrome(self, since: datetime) -> list[ContentItem]:
        """Parse Chrome browser history."""
        db_path = _CHROME_HISTORY_PATH
        if not db_path.exists():
            logger.debug("Chrome history DB not found at %s", db_path)
            return []

        since_chrome = int((since - _CHROME_EPOCH).total_seconds() * 1_000_000)
        rows = self._query_db(db_path, _CHROME_SQL, (since_chrome,))

        items: list[ContentItem] = []
        for row in rows:
            url, title, visit_count, last_visit_time = row
            if not self._passes_domain_filter(url):
                continue

            published_at = chrome_timestamp_to_datetime(last_visit_time)
            item_id = hashlib.sha256(url.encode()).hexdigest()[:16]

            items.append(
                ContentItem(
                    id=item_id,
                    url=url,
                    title=title or "",
                    source=ContentSource.BROWSER,
                    content_type=ContentType.WEBPAGE,
                    published_at=published_at,
                    metadata={"browser": "chrome", "visit_count": visit_count},
                )
            )

        return items

    def _parse_safari(self, since: datetime) -> list[ContentItem]:
        """Parse Safari browser history."""
        db_path = _SAFARI_HISTORY_PATH
        if not db_path.exists():
            logger.debug("Safari history DB not found at %s", db_path)
            return []

        rows = self._query_db(db_path, _SAFARI_SQL, ())

        since_safari = (since - _SAFARI_EPOCH).total_seconds()
        items: list[ContentItem] = []
        for row in rows:
            url, title, visit_time = row
            if visit_time < since_safari:
                continue
            if not self._passes_domain_filter(url):
                continue

            published_at = safari_timestamp_to_datetime(visit_time)
            item_id = hashlib.sha256(url.encode()).hexdigest()[:16]

            items.append(
                ContentItem(
                    id=item_id,
                    url=url,
                    title=title or "",
                    source=ContentSource.BROWSER,
                    content_type=ContentType.WEBPAGE,
                    published_at=published_at,
                    metadata={"browser": "safari"},
                )
            )

        return items

    def _passes_domain_filter(self, url: str) -> bool:
        """Check URL against domain allowlist/blocklist."""
        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            return False

        allowlist = self._config.browser.domain_allowlist
        blocklist = self._config.browser.domain_blocklist

        # If an allowlist is set, only allow matching domains
        if allowlist:
            return any(allowed.lower() in domain for allowed in allowlist)

        # Otherwise, reject blocked domains
        if blocklist:
            return not any(blocked.lower() in domain for blocked in blocklist)

        return True

    @staticmethod
    def _query_db(db_path: Path, sql: str, params: tuple) -> list[tuple]:
        """Copy the DB to a temp file and query it (browser holds a lock)."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
                shutil.copy2(db_path, tmp.name)
                conn = sqlite3.connect(tmp.name)
                try:
                    cursor = conn.execute(sql, params)
                    return cursor.fetchall()
                finally:
                    conn.close()
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Failed to query %s: %s", db_path, exc)
            return []

    @staticmethod
    def _dedup_by_url(items: list[ContentItem]) -> list[ContentItem]:
        """Deduplicate items by URL, keeping the first occurrence."""
        seen: set[str] = set()
        unique: list[ContentItem] = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        return unique
