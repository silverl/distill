"""YouTube liked videos and subscription parser."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_DAYS = 30

try:
    from googleapiclient.discovery import build as build_service

    _HAS_YOUTUBE_API = True
except ImportError:
    build_service = None  # type: ignore[assignment]
    _HAS_YOUTUBE_API = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi

    _HAS_TRANSCRIPT = True
except ImportError:
    YouTubeTranscriptApi = None  # type: ignore[assignment, misc]
    _HAS_TRANSCRIPT = False


class YouTubeParser(ContentParser):
    """Parses YouTube liked videos into ContentItem objects."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.YOUTUBE

    @property
    def is_configured(self) -> bool:
        return self._config.youtube.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        if not _HAS_YOUTUBE_API:
            logger.warning("google-api-python-client not installed, skipping YouTube")
            return []

        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=_DEFAULT_MAX_AGE_DAYS)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        service = self._build_service()
        if service is None:
            return []

        items = self._fetch_liked_videos(service, since)

        max_items = self._config.max_items_per_source
        if len(items) > max_items:
            items = items[:max_items]

        return items

    def _build_service(self):
        """Build the YouTube Data API service."""
        cfg = self._config.youtube

        if cfg.api_key:
            return build_service("youtube", "v3", developerKey=cfg.api_key)

        if cfg.credentials_file:
            from distill.intake.parsers import _google_auth

            creds = _google_auth.get_credentials(
                credentials_file=cfg.credentials_file,
                token_file=cfg.token_file or "",
                scopes=["https://www.googleapis.com/auth/youtube.readonly"],
            )
            if creds is None:
                logger.warning("YouTube OAuth credentials unavailable")
                return None
            return build_service("youtube", "v3", credentials=creds)

        logger.warning("No YouTube API key or credentials configured")
        return None

    def _fetch_liked_videos(self, service: object, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []
        page_token: str | None = None

        while True:
            request = service.videos().list(  # type: ignore[union-attr]
                myRating="like",
                part="snippet,contentDetails",
                maxResults=50,
                pageToken=page_token,
            )
            response = request.execute()

            for video in response.get("items", []):
                item = self._video_to_item(video, since)
                if item is not None:
                    items.append(item)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return items

    def _video_to_item(self, video: dict, since: datetime) -> ContentItem | None:
        snippet = video.get("snippet", {})
        video_id = video.get("id", "")
        if not video_id:
            return None

        published_str = snippet.get("publishedAt", "")
        published_at = self._parse_iso8601(published_str)

        if published_at and published_at < since:
            return None

        title = snippet.get("title", "")
        description = snippet.get("description", "")
        channel_title = snippet.get("channelTitle", "")
        tags = snippet.get("tags", []) or []

        url = f"https://www.youtube.com/watch?v={video_id}"
        item_id = hashlib.sha256(f"youtube-{video_id}".encode()).hexdigest()[:16]

        body = self._get_body(video_id, description)
        word_count = len(body.split()) if body else 0

        return ContentItem(
            id=item_id,
            url=url,
            title=title,
            body=body,
            excerpt=description[:500] if description else "",
            word_count=word_count,
            author=channel_title,
            site_name=channel_title,
            source=ContentSource.YOUTUBE,
            source_id=video_id,
            content_type=ContentType.VIDEO,
            tags=tags,
            published_at=published_at,
            metadata={"video_id": video_id},
        )

    def _get_body(self, video_id: str, description: str) -> str:
        """Get transcript if available and enabled, otherwise description."""
        if self._config.youtube.fetch_transcripts and _HAS_TRANSCRIPT:
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id)
                return " ".join(seg.get("text", "") for seg in transcript)
            except Exception:
                logger.debug("Transcript unavailable for %s, using description", video_id)

        return description

    @staticmethod
    def _parse_iso8601(date_str: str) -> datetime | None:
        if not date_str:
            return None
        try:
            # Handle ISO 8601 with Z suffix
            cleaned = date_str.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except ValueError:
            logger.debug("Failed to parse ISO 8601 date: %s", date_str)
            return None
