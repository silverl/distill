"""Intake context assembly for LLM synthesis."""

from __future__ import annotations

from datetime import date, datetime

from distill.intake.models import ContentItem, ContentSource
from pydantic import BaseModel, Field


class DailyIntakeContext(BaseModel):
    """Context for a daily intake synthesis."""

    date: date
    items: list[ContentItem] = Field(default_factory=list)
    total_items: int = 0
    total_word_count: int = 0
    sources: list[str] = Field(default_factory=list)
    sites: list[str] = Field(default_factory=list)
    all_tags: list[str] = Field(default_factory=list)
    combined_text: str = ""

    # Partitioned item lists for unified synthesis
    session_items: list[ContentItem] = Field(default_factory=list)
    seed_items: list[ContentItem] = Field(default_factory=list)
    content_items: list[ContentItem] = Field(default_factory=list)

    # Aggregated from session metadata
    projects_worked_on: list[str] = Field(default_factory=list)
    tools_used_today: list[str] = Field(default_factory=list)

    @property
    def has_sessions(self) -> bool:
        return len(self.session_items) > 0

    @property
    def has_seeds(self) -> bool:
        return len(self.seed_items) > 0


def _render_item(item: ContentItem) -> str:
    """Render a single item for LLM prompt."""
    header = f"## {item.title}" if item.title else "## (untitled)"
    meta_parts: list[str] = []
    if item.site_name:
        meta_parts.append(item.site_name)
    if item.author:
        meta_parts.append(f"by {item.author}")
    if item.url:
        meta_parts.append(item.url)
    meta_line = " | ".join(meta_parts)

    body = item.body or item.excerpt or "(no content)"
    if len(body) > 2000:
        body = body[:2000] + "\n\n[... truncated]"

    return f"{header}\n*{meta_line}*\n\n{body}"


def _render_session_section(sessions: list[ContentItem]) -> str:
    """Render sessions into a 'What You Built' section."""
    if not sessions:
        return ""

    parts: list[str] = ["# What You Built Today\n"]
    for item in sessions:
        project = item.metadata.get("project", "")
        duration = item.metadata.get("duration_minutes", "")
        tools = item.metadata.get("tools_used", [])
        tool_names = [t["name"] for t in tools if isinstance(t, dict)] if tools else []

        header = f"## {item.title}"
        meta: list[str] = []
        if project:
            meta.append(f"Project: {project}")
        if duration:
            meta.append(f"Duration: {duration}min")
        if tool_names:
            meta.append(f"Tools: {', '.join(tool_names[:5])}")

        body = item.body or "(no narrative)"
        if len(body) > 1500:
            body = body[:1500] + "\n\n[... truncated]"

        meta_line = " | ".join(meta) if meta else ""
        parts.append(f"{header}\n*{meta_line}*\n\n{body}")

    return "\n\n---\n\n".join(parts)


def _render_seed_section(seeds: list[ContentItem]) -> str:
    """Render seeds into a 'What You're Thinking About' section."""
    if not seeds:
        return ""

    parts: list[str] = ["# What You're Thinking About\n"]
    for item in seeds:
        tag_str = f" [{', '.join(item.tags)}]" if item.tags else ""
        parts.append(f"- {item.title}{tag_str}")

    return "\n".join(parts)


def _render_content_section(items: list[ContentItem]) -> str:
    """Render external content into a 'What You Read' section."""
    if not items:
        return ""

    sorted_items = sorted(items, key=lambda i: i.published_at or datetime.min, reverse=True)
    prompt_items = sorted_items[:50]

    parts: list[str] = ["# What You Read Today\n"]
    for item in prompt_items:
        parts.append(_render_item(item))

    return "\n\n---\n\n".join(parts)


def prepare_daily_context(
    items: list[ContentItem],
    target_date: date | None = None,
    clustered_text: str = "",
) -> DailyIntakeContext:
    """Assemble context for daily intake synthesis.

    Args:
        items: Content items to include.
        target_date: The date for this digest. Defaults to today.
        clustered_text: Pre-rendered topic-clustered context from the
            clustering module.  When provided, this replaces the flat
            article list in ``combined_text`` for better thematic
            grouping in the LLM prompt.

    Returns:
        Fully assembled DailyIntakeContext.
    """
    if target_date is None:
        target_date = date.today()

    total_word_count = sum(i.word_count for i in items)

    # Partition items by source type
    session_items: list[ContentItem] = []
    seed_items: list[ContentItem] = []
    content_items: list[ContentItem] = []

    for item in items:
        if item.source == ContentSource.SESSION:
            session_items.append(item)
        elif item.source == ContentSource.SEEDS:
            seed_items.append(item)
        else:
            content_items.append(item)

    # Aggregate projects and tools from session metadata
    projects: list[str] = []
    tools: list[str] = []
    seen_projects: set[str] = set()
    seen_tools: set[str] = set()

    for item in session_items:
        project = item.metadata.get("project")
        if isinstance(project, str) and project and project not in seen_projects:
            projects.append(project)
            seen_projects.add(project)
        item_tools = item.metadata.get("tools_used", [])
        if isinstance(item_tools, list):
            for t in item_tools:
                if isinstance(t, dict):
                    name = t.get("name", "")
                    if name and name not in seen_tools:
                        tools.append(name)
                        seen_tools.add(name)

    # Collect unique sources and sites
    sources: list[str] = []
    sites: list[str] = []
    tags: list[str] = []
    seen_sources: set[str] = set()
    seen_sites: set[str] = set()
    seen_tags: set[str] = set()

    for item in items:
        src = item.source.value
        if src not in seen_sources:
            sources.append(src)
            seen_sources.add(src)
        if item.site_name and item.site_name not in seen_sites:
            sites.append(item.site_name)
            seen_sites.add(item.site_name)
        for tag in item.tags:
            if tag not in seen_tags:
                tags.append(tag)
                seen_tags.add(tag)

    # Build combined text for LLM prompt
    if clustered_text and not session_items and not seed_items:
        # Use topic-clustered context only when no sessions/seeds
        combined_text = clustered_text
    else:
        # Build unified context with sections
        sections: list[str] = []

        if session_items:
            sections.append(_render_session_section(session_items))

        if seed_items:
            sections.append(_render_seed_section(seed_items))

        if content_items:
            if clustered_text:
                sections.append(f"# What You Read Today\n\n{clustered_text}")
            else:
                sections.append(_render_content_section(content_items))

        combined_text = "\n\n" + "\n\n".join(sections) if sections else ""

    return DailyIntakeContext(
        date=target_date,
        items=items,
        total_items=len(items),
        total_word_count=total_word_count,
        sources=sources,
        sites=sites,
        all_tags=tags,
        combined_text=combined_text,
        session_items=session_items,
        seed_items=seed_items,
        content_items=content_items,
        projects_worked_on=projects,
        tools_used_today=tools,
    )
