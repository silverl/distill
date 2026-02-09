"""Blog-level memory for cross-referencing across posts.

Tracks summaries of published blog posts so new posts can reference
previous work naturally, creating a coherent body of content over time.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MEMORY_FILENAME = ".blog-memory.json"


class BlogPostSummary(BaseModel):
    """Summary of a published blog post for cross-referencing."""

    slug: str
    title: str
    post_type: str  # "weekly" or "thematic"
    date: date
    key_points: list[str] = Field(default_factory=list)
    themes_covered: list[str] = Field(default_factory=list)
    examples_used: list[str] = Field(default_factory=list)
    platforms_published: list[str] = Field(default_factory=list)
    postiz_ids: list[str] = Field(default_factory=list)


class BlogMemory(BaseModel):
    """Rolling memory of published blog content."""

    posts: list[BlogPostSummary] = Field(default_factory=list)

    def render_for_prompt(self) -> str:
        """Render as context for LLM injection.

        Returns empty string if no posts exist. Includes dedup section
        listing examples/anecdotes already used across previous posts.
        """
        if not self.posts:
            return ""

        lines: list[str] = ["## Previous Blog Posts", ""]
        for post in sorted(self.posts, key=lambda p: p.date, reverse=True):
            points = "; ".join(post.key_points) if post.key_points else "no summary"
            lines.append(f'- "{post.title}" ({post.date.isoformat()}): {points}')
        lines.append("")

        # Collect all examples used across posts for dedup
        all_examples: list[str] = []
        for post in self.posts:
            all_examples.extend(post.examples_used)
        if all_examples:
            lines.append("## DO NOT REUSE These Examples")
            lines.append(
                "The following specific examples, anecdotes, bugs, and statistics"
                " have already been used in previous posts. Find DIFFERENT"
                " evidence from the journal entries. Never recycle these:"
            )
            lines.append("")
            for ex in sorted(set(all_examples)):
                lines.append(f"- {ex}")
            lines.append("")

        return "\n".join(lines)

    def add_post(self, summary: BlogPostSummary) -> None:
        """Add or replace a post summary by slug."""
        self.posts = [p for p in self.posts if p.slug != summary.slug]
        self.posts.append(summary)

    def is_published_to(self, slug: str, platform: str) -> bool:
        """Check if a post has been published to a platform."""
        for post in self.posts:
            if post.slug == slug and platform in post.platforms_published:
                return True
        return False

    def mark_published(self, slug: str, platform: str) -> None:
        """Add platform to a post's platforms_published list."""
        for post in self.posts:
            if post.slug == slug and platform not in post.platforms_published:
                post.platforms_published.append(platform)
                return


def load_blog_memory(output_dir: Path) -> BlogMemory:
    """Load blog memory from disk.

    Returns empty BlogMemory if file doesn't exist or is corrupt.
    """
    memory_path = output_dir / "blog" / MEMORY_FILENAME
    if not memory_path.exists():
        return BlogMemory()
    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
        return BlogMemory.model_validate(data)
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Corrupt blog memory at %s, starting fresh", memory_path)
        return BlogMemory()


def save_blog_memory(memory: BlogMemory, output_dir: Path) -> None:
    """Save blog memory to disk."""
    memory_path = output_dir / "blog" / MEMORY_FILENAME
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        memory.model_dump_json(indent=2),
        encoding="utf-8",
    )
