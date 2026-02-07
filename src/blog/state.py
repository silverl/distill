"""Blog state tracking to avoid duplicate generation.

Persists a record of which blog posts have been generated, their source
dates, and output paths.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

STATE_FILENAME = ".blog-state.json"


class BlogPostRecord(BaseModel):
    """Record of a generated blog post."""

    slug: str
    post_type: str
    generated_at: datetime
    source_dates: list[date] = Field(default_factory=list)
    file_path: str = ""


class BlogState(BaseModel):
    """Tracks what blog posts have been generated."""

    posts: list[BlogPostRecord] = Field(default_factory=list)

    def is_generated(self, slug: str) -> bool:
        """Check if a blog post with this slug has already been generated."""
        return any(p.slug == slug for p in self.posts)

    def mark_generated(self, record: BlogPostRecord) -> None:
        """Record that a blog post was generated.

        Replaces any existing record with the same slug.
        """
        self.posts = [p for p in self.posts if p.slug != record.slug]
        self.posts.append(record)


def load_blog_state(output_dir: Path) -> BlogState:
    """Load blog state from disk.

    Returns empty BlogState if file doesn't exist or is corrupt.
    """
    state_path = output_dir / "blog" / STATE_FILENAME
    if not state_path.exists():
        return BlogState()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return BlogState.model_validate(data)
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Corrupt blog state at %s, starting fresh", state_path)
        return BlogState()


def save_blog_state(state: BlogState, output_dir: Path) -> None:
    """Save blog state to disk."""
    state_path = output_dir / "blog" / STATE_FILENAME
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )
