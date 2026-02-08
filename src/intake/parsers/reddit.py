"""Reddit saved/upvoted content parser."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

try:
    import praw

    _HAS_PRAW = True
except ImportError:
    praw = None  # type: ignore[assignment]
    _HAS_PRAW = False


class RedditParser(ContentParser):
    """Parses saved and upvoted Reddit posts into ContentItem objects."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.REDDIT

    @property
    def is_configured(self) -> bool:
        return self._config.reddit.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        """Fetch saved and upvoted Reddit content.

        Args:
            since: Only return items created after this time.
                   When None, defaults to last 30 days.

        Returns:
            Deduplicated list of ContentItem objects.
        """
        if not _HAS_PRAW:
            logger.warning("praw not installed. pip install praw")
            return []

        if not self.is_configured:
            return []

        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=30)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        reddit = praw.Reddit(
            client_id=self._config.reddit.client_id,
            client_secret=self._config.reddit.client_secret,
            username=self._config.reddit.username,
            password=self._config.reddit.password,
            user_agent="distill-intake/1.0",
        )

        seen: dict[str, ContentItem] = {}
        limit = self._config.max_items_per_source

        # Fetch saved items
        for thing in reddit.user.me().saved(limit=limit):
            item = self._thing_to_item(thing, is_starred=True, since=since)
            if item and item.source_id not in seen:
                seen[item.source_id] = item

        # Fetch upvoted items
        for thing in reddit.user.me().upvoted(limit=limit):
            item = self._thing_to_item(thing, is_starred=False, since=since)
            if item and item.source_id not in seen:
                seen[item.source_id] = item

        items = list(seen.values())[:limit]
        logger.info("Parsed %d items from Reddit", len(items))
        return items

    @staticmethod
    def _thing_to_item(
        thing: object,
        *,
        is_starred: bool,
        since: datetime,
    ) -> ContentItem | None:
        """Convert a praw Submission or Comment to a ContentItem."""
        thing_id = getattr(thing, "id", "")
        created_utc = getattr(thing, "created_utc", 0.0)
        created_at = datetime.fromtimestamp(created_utc, tz=UTC)

        if created_at < since:
            return None

        item_id = hashlib.sha256(f"reddit-{thing_id}".encode()).hexdigest()[:16]

        # Comments
        if hasattr(thing, "body") and not hasattr(thing, "title"):
            body = getattr(thing, "body", "")
            author = str(getattr(thing, "author", "")) if getattr(thing, "author", None) else ""
            subreddit = str(getattr(thing, "subreddit", ""))
            score = getattr(thing, "score", 0)
            url = getattr(thing, "permalink", "")
            if url and not url.startswith("http"):
                url = f"https://reddit.com{url}"

            return ContentItem(
                id=item_id,
                url=url,
                title="",
                body=body,
                word_count=len(body.split()) if body else 0,
                author=author,
                source=ContentSource.REDDIT,
                source_id=thing_id,
                content_type=ContentType.COMMENT,
                tags=[subreddit] if subreddit else [],
                published_at=created_at,
                is_starred=is_starred,
                metadata={"score": score},
            )

        # Submissions
        title = getattr(thing, "title", "")
        selftext = getattr(thing, "selftext", "")
        url = getattr(thing, "url", "")
        permalink = getattr(thing, "permalink", "")
        author = str(getattr(thing, "author", "")) if getattr(thing, "author", None) else ""
        subreddit = str(getattr(thing, "subreddit", ""))
        score = getattr(thing, "score", 0)

        # Determine content type: link posts are ARTICLE, self-posts are POST
        is_self = getattr(thing, "is_self", bool(selftext and not url))
        if is_self:
            content_type = ContentType.POST
            body = selftext
            item_url = f"https://reddit.com{permalink}" if permalink else url
        else:
            content_type = ContentType.ARTICLE
            body = selftext or ""
            item_url = url

        return ContentItem(
            id=item_id,
            url=item_url,
            title=title,
            body=body,
            word_count=len(body.split()) if body else 0,
            author=author,
            source=ContentSource.REDDIT,
            source_id=thing_id,
            content_type=content_type,
            tags=[subreddit] if subreddit else [],
            published_at=created_at,
            is_starred=is_starred,
            metadata={"score": score},
        )
