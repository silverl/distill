"""Canonical content models — source-agnostic data types."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ContentSource(StrEnum):
    """Supported content sources."""

    RSS = "rss"
    GMAIL = "gmail"
    SUBSTACK = "substack"
    BROWSER = "browser"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    TWITTER = "twitter"
    SESSION = "session"
    SEEDS = "seeds"
    MANUAL = "manual"


class ContentType(StrEnum):
    """Content format categories."""

    ARTICLE = "article"
    NEWSLETTER = "newsletter"
    POST = "post"
    COMMENT = "comment"
    VIDEO = "video"
    THREAD = "thread"
    WEBPAGE = "webpage"


class Highlight(BaseModel):
    """A highlighted passage from a content item."""

    text: str
    note: str = ""
    position: int = 0


class ContentItem(BaseModel):
    """Source-agnostic content item — the canonical model.

    Every source parser produces these. The core pipeline operates
    entirely on ``ContentItem[]`` and never knows which source
    produced an item. Analogous to ``BaseSession`` in the session
    parsing pipeline.
    """

    id: str
    url: str = ""
    title: str = ""
    body: str = ""
    excerpt: str = ""
    word_count: int = 0
    author: str = ""
    site_name: str = ""
    source: ContentSource
    source_id: str = ""
    content_type: ContentType = ContentType.ARTICLE
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    saved_at: datetime = Field(default_factory=datetime.now)
    consumed_at: datetime | None = None
    is_starred: bool = False
    highlights: list[Highlight] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
