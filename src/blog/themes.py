"""Theme registry for thematic deep-dive blog posts.

Defines the themes that can trigger thematic blog posts. Each theme has
keywords and thread patterns used for evidence gathering from journal entries.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from distill.blog.reader import JournalEntry
from distill.blog.state import BlogState


class ThemeDefinition(BaseModel):
    """A blog-worthy theme with detection criteria."""

    slug: str
    title: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    thread_patterns: list[str] = Field(default_factory=list)
    min_evidence_days: int = 3


THEMES: list[ThemeDefinition] = [
    ThemeDefinition(
        slug="coordination-overhead",
        title="When Coordination Overhead Exceeds Task Value",
        description="Explores the costs of multi-agent coordination relative to task complexity.",
        keywords=["ceremony", "overhead", "coordination", "granularity"],
        thread_patterns=["coordination", "ceremony", "overhead"],
    ),
    ThemeDefinition(
        slug="quality-gates-that-work",
        title="Quality Gates That Actually Work",
        description="Examines which QA patterns catch real bugs vs create busywork.",
        keywords=["QA", "revision", "caught", "quality gate"],
        thread_patterns=["qa", "quality", "review"],
    ),
    ThemeDefinition(
        slug="infrastructure-vs-shipping",
        title="Infrastructure Building vs Shipping Features",
        description="The tension between building tooling and delivering user-visible results.",
        keywords=["validation theater", "infrastructure", "shipping", "user-visible"],
        thread_patterns=["validation", "infrastructure", "shipping"],
    ),
    ThemeDefinition(
        slug="branch-merge-failures",
        title="Why Branch Merges Keep Failing",
        description="Root causes of merge failures in multi-agent branch workflows.",
        keywords=["merge", "branch", "direct-to-main", "worktree"],
        thread_patterns=["merge", "branch", "worktree"],
    ),
    ThemeDefinition(
        slug="meta-work-recursion",
        title="When Introspection Systems Become Obstacles",
        description="How tools built to analyze work can themselves become the work.",
        keywords=["meta-work", "recursion", "introspection", "analyzing"],
        thread_patterns=["meta-work", "recursion", "reflection"],
    ),
    ThemeDefinition(
        slug="visibility-gap",
        title="What Your Coordination System Can't See",
        description="Blind spots in agent orchestration and repository state tracking.",
        keywords=["visibility", "blind", "git status", "repository state"],
        thread_patterns=["visibility", "blind"],
    ),
]


def gather_evidence(
    theme: ThemeDefinition, entries: list[JournalEntry]
) -> list[JournalEntry]:
    """Find journal entries that contain evidence for a theme.

    Searches both prose content (via keywords) and tags (via thread patterns).
    """
    matching: list[JournalEntry] = []
    for entry in entries:
        if _entry_matches_theme(entry, theme):
            matching.append(entry)
    return matching


def get_ready_themes(
    entries: list[JournalEntry], state: BlogState
) -> list[tuple[ThemeDefinition, list[JournalEntry]]]:
    """Find themes with enough evidence that haven't been blogged yet.

    Returns tuples of (theme, evidence_entries) for themes that meet the
    minimum evidence threshold and haven't already been generated.
    """
    ready: list[tuple[ThemeDefinition, list[JournalEntry]]] = []
    for theme in THEMES:
        if state.is_generated(theme.slug):
            continue
        evidence = gather_evidence(theme, entries)
        unique_dates = {e.date for e in evidence}
        if len(unique_dates) >= theme.min_evidence_days:
            ready.append((theme, evidence))
    return ready


def _entry_matches_theme(entry: JournalEntry, theme: ThemeDefinition) -> bool:
    """Check if a journal entry matches a theme via keywords or patterns."""
    prose_lower = entry.prose.lower()

    # Check keywords in prose
    for keyword in theme.keywords:
        if keyword.lower() in prose_lower:
            return True

    # Check thread patterns against tags
    tags_lower = [t.lower() for t in entry.tags]
    for pattern in theme.thread_patterns:
        pattern_lower = pattern.lower()
        for tag in tags_lower:
            if pattern_lower in tag:
                return True

    return False
