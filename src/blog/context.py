"""Blog context assembly for weekly and thematic posts.

Two context types, one per blog post type. Each aggregates journal entries
and working memory into a structured context suitable for LLM prompts.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from distill.blog.reader import JournalEntry
from distill.blog.themes import ThemeDefinition
from distill.journal.memory import MemoryThread, WorkingMemory


class WeeklyBlogContext(BaseModel):
    """Context for a weekly synthesis blog post."""

    year: int
    week: int
    week_start: date
    week_end: date
    entries: list[JournalEntry] = Field(default_factory=list)
    total_sessions: int = 0
    total_duration_minutes: float = 0.0
    projects: list[str] = Field(default_factory=list)
    all_tags: list[str] = Field(default_factory=list)
    working_memory: str = ""
    combined_prose: str = ""


class ThematicBlogContext(BaseModel):
    """Context for a thematic deep-dive blog post."""

    theme: ThemeDefinition
    evidence_entries: list[JournalEntry] = Field(default_factory=list)
    date_range: tuple[date, date] = (date.min, date.min)
    evidence_count: int = 0
    relevant_threads: list[MemoryThread] = Field(default_factory=list)
    combined_evidence: str = ""


def prepare_weekly_context(
    entries: list[JournalEntry],
    year: int,
    week: int,
    memory: WorkingMemory | None = None,
) -> WeeklyBlogContext:
    """Assemble context for a weekly synthesis post.

    Args:
        entries: Journal entries for the target week.
        year: ISO year.
        week: ISO week number.
        memory: Optional working memory for narrative continuity.

    Returns:
        Fully assembled weekly blog context.
    """
    # Compute week start/end (Monday to Sunday)
    week_start = date.fromisocalendar(year, week, 1)
    week_end = week_start + timedelta(days=6)

    # Aggregate stats
    total_sessions = sum(e.sessions_count for e in entries)
    total_duration = sum(e.duration_minutes for e in entries)

    # Collect unique projects and tags
    projects: list[str] = []
    tags: list[str] = []
    seen_projects: set[str] = set()
    seen_tags: set[str] = set()

    for entry in entries:
        for p in entry.projects:
            if p not in seen_projects:
                projects.append(p)
                seen_projects.add(p)
        for t in entry.tags:
            if t not in seen_tags:
                tags.append(t)
                seen_tags.add(t)

    # Combine prose from all entries
    prose_parts: list[str] = []
    for entry in sorted(entries, key=lambda e: e.date):
        day_label = entry.date.strftime("%A, %B %d")
        prose_parts.append(f"## {day_label}\n\n{entry.prose}")
    combined_prose = "\n\n".join(prose_parts)

    # Render working memory if available
    working_memory_text = ""
    if memory is not None:
        working_memory_text = memory.render_for_prompt()

    return WeeklyBlogContext(
        year=year,
        week=week,
        week_start=week_start,
        week_end=week_end,
        entries=entries,
        total_sessions=total_sessions,
        total_duration_minutes=total_duration,
        projects=projects,
        all_tags=tags,
        working_memory=working_memory_text,
        combined_prose=combined_prose,
    )


def prepare_thematic_context(
    theme: ThemeDefinition,
    evidence: list[JournalEntry],
    memory: WorkingMemory | None = None,
) -> ThematicBlogContext:
    """Assemble context for a thematic deep-dive post.

    Args:
        theme: The theme to write about.
        evidence: Journal entries containing evidence for the theme.
        memory: Optional working memory for thread matching.

    Returns:
        Fully assembled thematic blog context.
    """
    if not evidence:
        return ThematicBlogContext(theme=theme)

    # Date range
    dates = sorted(e.date for e in evidence)
    date_range = (dates[0], dates[-1])

    # Find relevant threads from working memory
    relevant_threads: list[MemoryThread] = []
    if memory is not None:
        for thread in memory.threads:
            thread_name_lower = thread.name.lower()
            for pattern in theme.thread_patterns:
                if pattern.lower() in thread_name_lower:
                    relevant_threads.append(thread)
                    break

    # Combine evidence prose
    evidence_parts: list[str] = []
    for entry in sorted(evidence, key=lambda e: e.date):
        day_label = entry.date.strftime("%B %d, %Y")
        evidence_parts.append(f"### {day_label}\n\n{entry.prose}")
    combined_evidence = "\n\n".join(evidence_parts)

    return ThematicBlogContext(
        theme=theme,
        evidence_entries=evidence,
        date_range=date_range,
        evidence_count=len(evidence),
        relevant_threads=relevant_threads,
        combined_evidence=combined_evidence,
    )
