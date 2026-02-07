"""Configuration models for blog generation."""

from enum import Enum

from pydantic import BaseModel


class BlogPostType(str, Enum):
    """Available blog post types."""

    WEEKLY = "weekly"
    THEMATIC = "thematic"


class BlogConfig(BaseModel):
    """Configuration for blog post generation."""

    target_word_count: int = 1200
    include_diagrams: bool = True
    model: str | None = None
    claude_timeout: int = 180
