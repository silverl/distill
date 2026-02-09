"""Theme registry for thematic deep-dive blog posts.

Defines the themes that can trigger thematic blog posts. Each theme has
keywords and thread patterns used for evidence gathering from journal entries.
"""

from __future__ import annotations

from distill.blog.reader import JournalEntry
from distill.blog.state import BlogState
from pydantic import BaseModel, Field


class ThemeDefinition(BaseModel):
    """A blog-worthy theme with detection criteria."""

    slug: str
    title: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    thread_patterns: list[str] = Field(default_factory=list)
    min_evidence_days: int = 3


THEMES: list[ThemeDefinition] = [
    # Achievement / what-works themes
    ThemeDefinition(
        slug="healthy-friction-works",
        title="How Healthy Friction Between Agents Catches Real Bugs",
        description=(
            "QA-dev friction as a quality multiplier"
            " — when structured disagreement produces better code."
        ),
        keywords=["healthy friction", "caught", "revision", "coverage gap", "real bug"],
        thread_patterns=["healthy-friction", "qa-dev", "friction"],
    ),
    ThemeDefinition(
        slug="pipeline-that-compounds",
        title="Building a Content Pipeline That Compounds",
        description=(
            "How a system that ingests sessions, reads, and thoughts"
            " produces richer output over time."
        ),
        keywords=["pipeline", "compound", "memory", "continuity", "narrative"],
        thread_patterns=["pipeline", "compound", "memory"],
    ),
    ThemeDefinition(
        slug="mission-cycles-that-chain",
        title="When Mission Cycles Start Chaining Autonomously",
        description="The moment multi-agent workflows go from orchestrated to self-sustaining.",
        keywords=["chaining", "autonomous", "mission cycle", "self-sustaining", "pipeline"],
        thread_patterns=["mission-cycle", "chaining", "autonomous"],
    ),
    ThemeDefinition(
        slug="self-referential-loop",
        title="The Self-Referential AI Tooling Loop",
        description=(
            "Building tools where the AI watches itself work, then learns from what it sees."
        ),
        keywords=["self-referential", "meta-learning", "knowledge extraction", "self-improving"],
        thread_patterns=["self-referential", "self-improvement", "knowledge-extraction"],
    ),
    # Challenge / learning themes
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


def gather_evidence(theme: ThemeDefinition, entries: list[JournalEntry]) -> list[JournalEntry]:
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


def themes_from_seeds(seeds: list[object]) -> list[ThemeDefinition]:
    """Convert unused seed ideas into dynamic blog themes.

    Each seed becomes a theme. The seed text is the title, and keywords
    are derived from the seed's tags plus key words from the text.

    Args:
        seeds: List of SeedIdea objects (has .id, .text, .tags attributes).

    Returns:
        List of ThemeDefinition objects ready for evidence gathering.
    """
    themes: list[ThemeDefinition] = []
    for seed in seeds:
        # Build keywords from tags + significant words in the text
        text = seed.text  # type: ignore[union-attr]
        tags = list(seed.tags) if hasattr(seed, "tags") else []  # type: ignore[union-attr]

        # Extract meaningful words (>4 chars, not stopwords) as keywords
        stopwords = {
            "about",
            "after",
            "before",
            "being",
            "between",
            "could",
            "every",
            "from",
            "have",
            "into",
            "more",
            "most",
            "much",
            "only",
            "over",
            "should",
            "some",
            "such",
            "than",
            "that",
            "their",
            "them",
            "then",
            "there",
            "these",
            "they",
            "this",
            "through",
            "under",
            "very",
            "what",
            "when",
            "where",
            "which",
            "while",
            "with",
            "would",
            "your",
        }
        words = [
            w.strip(".,;:!?\"'()—-")
            for w in text.lower().split()
            if len(w.strip(".,;:!?\"'()—-")) > 4 and w.strip(".,;:!?\"'()—-") not in stopwords
        ]
        keywords = tags + words[:8]

        # Slug from seed ID
        slug = f"seed-{seed.id}"  # type: ignore[union-attr]

        themes.append(
            ThemeDefinition(
                slug=slug,
                title=text,
                description=f"Blog post exploring: {text}",
                keywords=keywords,
                thread_patterns=tags if tags else words[:3],
                min_evidence_days=1,  # Seeds need less evidence — the seed IS the angle
            )
        )
    return themes


def detect_series_candidates(
    entries: list[JournalEntry],
    memory: object,
    state: object,
) -> list[ThemeDefinition]:
    """Find series-worthy topics from memory threads and entities.

    Looks for threads with high mention counts and entities with high
    frequency that haven't been blogged yet.

    Args:
        entries: Journal entries.
        memory: UnifiedMemory instance.
        state: BlogState instance.

    Returns:
        List of ThemeDefinition objects for series candidates.
    """
    from distill.blog.state import BlogState
    from distill.memory import UnifiedMemory

    if not isinstance(memory, UnifiedMemory) or not isinstance(state, BlogState):
        return []

    candidates: list[ThemeDefinition] = []

    # Series from threads with mention_count >= 3
    for thread in memory.threads:
        if thread.status != "active":
            continue
        if thread.mention_count < 3:
            continue
        slug = f"series-{thread.name.lower().replace(' ', '-')}"
        if state.is_generated(slug):
            continue
        candidates.append(
            ThemeDefinition(
                slug=slug,
                title=f"Series: {thread.name}",
                description=thread.summary,
                keywords=[thread.name.lower()],
                thread_patterns=[thread.name.lower()],
                min_evidence_days=2,
            )
        )

    # Series from entities with mention_count >= 5
    for _key, entity in memory.entities.items():
        if entity.mention_count < 5:
            continue
        slug = f"series-{entity.name.lower().replace(' ', '-')}"
        if state.is_generated(slug):
            continue
        candidates.append(
            ThemeDefinition(
                slug=slug,
                title=f"Deep Dive: {entity.name}",
                description=f"Extended exploration of {entity.name} ({entity.entity_type})",
                keywords=[entity.name.lower()],
                thread_patterns=[entity.name.lower()],
                min_evidence_days=2,
            )
        )

    return candidates


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
