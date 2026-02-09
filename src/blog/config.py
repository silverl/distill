"""Configuration models for blog generation."""

import os
from enum import StrEnum

from pydantic import BaseModel, Field


class BlogPostType(StrEnum):
    """Available blog post types."""

    WEEKLY = "weekly"
    THEMATIC = "thematic"
    READING_LIST = "reading-list"


class Platform(StrEnum):
    """Available publishing platforms."""

    OBSIDIAN = "obsidian"
    GHOST = "ghost"
    MARKDOWN = "markdown"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"
    POSTIZ = "postiz"


class GhostConfig(BaseModel):
    """Configuration for Ghost CMS publishing."""

    url: str = ""
    admin_api_key: str = ""
    newsletter_slug: str = ""
    auto_publish: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.admin_api_key)

    @classmethod
    def from_env(cls) -> "GhostConfig":
        """Create config from environment variables."""
        return cls(
            url=os.environ.get("GHOST_URL", ""),
            admin_api_key=os.environ.get("GHOST_ADMIN_API_KEY", ""),
            newsletter_slug=os.environ.get("GHOST_NEWSLETTER_SLUG", ""),
        )


class BlogConfig(BaseModel):
    """Configuration for blog post generation."""

    target_word_count: int = 1200
    include_diagrams: bool = True
    model: str | None = None
    claude_timeout: int = 360
    platforms: list[Platform] = Field(default_factory=lambda: [Platform.OBSIDIAN])
    ghost: GhostConfig = Field(default_factory=GhostConfig)
