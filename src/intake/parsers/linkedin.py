"""LinkedIn GDPR data export parser."""

from __future__ import annotations

import csv
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 30

# Date formats used in LinkedIn GDPR exports
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y",
]


def _parse_date(raw: str) -> datetime | None:
    """Try multiple date formats used by LinkedIn exports."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    logger.warning("Could not parse LinkedIn date: %s", raw)
    return None


def _stable_id(value: str) -> str:
    """Generate a stable 16-char hex ID from a string."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


class LinkedInParser(ContentParser):
    """Parses LinkedIn GDPR data export CSV files into ContentItem objects."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.LINKEDIN

    @property
    def is_configured(self) -> bool:
        return self._config.linkedin.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        """Parse LinkedIn export CSVs into ContentItem objects.

        Args:
            since: Only return items after this time.
                   Defaults to 30 days ago if None.

        Returns:
            Deduplicated list of ContentItem objects.
        """
        export_path = Path(self._config.linkedin.export_path)
        if not export_path.is_dir():
            logger.warning("LinkedIn export path not found: %s", export_path)
            return []

        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_MAX_AGE_DAYS)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        items: list[ContentItem] = []
        items.extend(self._parse_shares(export_path, since))
        items.extend(self._parse_articles(export_path, since))
        items.extend(self._parse_saved_articles(export_path, since))
        items.extend(self._parse_reactions(export_path, since))

        items = self._dedup_by_url(items)

        # Apply max_items_per_source limit
        max_items = self._config.max_items_per_source
        if len(items) > max_items:
            items = items[:max_items]

        logger.info("Parsed %d items from LinkedIn export", len(items))
        return items

    def _parse_shares(self, export_path: Path, since: datetime) -> list[ContentItem]:
        """Parse Shares.csv — posts shared by the user."""
        csv_path = export_path / "Shares.csv"
        if not csv_path.exists():
            logger.debug("No Shares.csv found in %s", export_path)
            return []

        items: list[ContentItem] = []
        for row in self._read_csv(csv_path):
            date_str = row.get("Date", "")
            published_at = _parse_date(date_str)
            if published_at and published_at < since:
                continue

            url = row.get("ShareLink", "") or row.get("SharedUrl", "")
            commentary = row.get("ShareCommentary", "")
            shared_url = row.get("SharedUrl", "")
            media_url = row.get("MediaUrl", "")

            id_source = url or commentary
            if not id_source:
                continue

            body = commentary
            if shared_url and shared_url != url:
                body = f"{commentary}\n\nShared: {shared_url}" if commentary else shared_url
            if media_url:
                body = f"{body}\n\nMedia: {media_url}" if body else media_url

            items.append(
                ContentItem(
                    id=_stable_id(id_source),
                    url=url,
                    title=commentary[:100] if commentary else "",
                    body=body,
                    excerpt=commentary[:500] if commentary else "",
                    word_count=len(body.split()) if body else 0,
                    source=ContentSource.LINKEDIN,
                    source_id=url,
                    content_type=ContentType.POST,
                    published_at=published_at,
                    metadata={"csv": "Shares.csv"},
                )
            )

        return items

    def _parse_articles(self, export_path: Path, since: datetime) -> list[ContentItem]:
        """Parse Articles.csv — articles published by the user."""
        csv_path = export_path / "Articles.csv"
        if not csv_path.exists():
            logger.debug("No Articles.csv found in %s", export_path)
            return []

        items: list[ContentItem] = []
        for row in self._read_csv(csv_path):
            date_str = row.get("Date", "")
            published_at = _parse_date(date_str)
            if published_at and published_at < since:
                continue

            title = row.get("Title", "")
            content = row.get("Content", "")
            url = row.get("ArticleLink", "")

            id_source = url or title
            if not id_source:
                continue

            items.append(
                ContentItem(
                    id=_stable_id(id_source),
                    url=url,
                    title=title,
                    body=content,
                    excerpt=content[:500] if content else "",
                    word_count=len(content.split()) if content else 0,
                    source=ContentSource.LINKEDIN,
                    source_id=url or title,
                    content_type=ContentType.ARTICLE,
                    published_at=published_at,
                    metadata={"csv": "Articles.csv"},
                )
            )

        return items

    def _parse_saved_articles(self, export_path: Path, since: datetime) -> list[ContentItem]:
        """Parse SavedArticles.csv or Saved Articles.csv."""
        csv_path = export_path / "SavedArticles.csv"
        if not csv_path.exists():
            csv_path = export_path / "Saved Articles.csv"
        if not csv_path.exists():
            logger.debug("No saved articles CSV found in %s", export_path)
            return []

        items: list[ContentItem] = []
        for row in self._read_csv(csv_path):
            date_str = row.get("Date", "")
            published_at = _parse_date(date_str)
            if published_at and published_at < since:
                continue

            title = row.get("Title", "")
            url = row.get("Url", "") or row.get("Link", "")

            id_source = url or title
            if not id_source:
                continue

            items.append(
                ContentItem(
                    id=_stable_id(id_source),
                    url=url,
                    title=title,
                    source=ContentSource.LINKEDIN,
                    source_id=url or title,
                    content_type=ContentType.ARTICLE,
                    is_starred=True,
                    published_at=published_at,
                    metadata={"csv": "SavedArticles.csv"},
                )
            )

        return items

    def _parse_reactions(self, export_path: Path, since: datetime) -> list[ContentItem]:
        """Parse Reactions.csv — content liked/reacted to."""
        csv_path = export_path / "Reactions.csv"
        if not csv_path.exists():
            logger.debug("No Reactions.csv found in %s", export_path)
            return []

        items: list[ContentItem] = []
        for row in self._read_csv(csv_path):
            date_str = row.get("Date", "")
            published_at = _parse_date(date_str)
            if published_at and published_at < since:
                continue

            reaction_type = row.get("Type", "")
            url = row.get("Link", "")

            if not url:
                continue

            items.append(
                ContentItem(
                    id=_stable_id(url),
                    url=url,
                    title=f"Liked ({reaction_type})" if reaction_type else "Liked",
                    source=ContentSource.LINKEDIN,
                    source_id=url,
                    content_type=ContentType.ARTICLE,
                    published_at=published_at,
                    metadata={"csv": "Reactions.csv", "reaction_type": reaction_type},
                )
            )

        return items

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """Read a CSV file, returning rows as dicts. Handles malformed rows."""
        rows: list[dict[str, str]] = []
        try:
            text = path.read_text(encoding="utf-8")
            reader = csv.DictReader(text.splitlines())
            for row in reader:
                try:
                    rows.append(dict(row))
                except Exception:
                    logger.debug("Skipping malformed row in %s", path)
        except Exception:
            logger.warning("Failed to read CSV: %s", path, exc_info=True)
        return rows

    @staticmethod
    def _dedup_by_url(items: list[ContentItem]) -> list[ContentItem]:
        """Deduplicate items by URL, keeping the first occurrence."""
        seen: set[str] = set()
        unique: list[ContentItem] = []
        for item in items:
            if not item.url:
                unique.append(item)
                continue
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        return unique
