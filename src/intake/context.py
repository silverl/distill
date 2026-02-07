"""Intake context assembly for LLM synthesis."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from distill.intake.models import ContentItem


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
    if clustered_text:
        # Use topic-clustered context for better thematic grouping
        combined_text = clustered_text
    else:
        # Fallback: flat list sorted by recency, capped at 50
        sorted_items = sorted(
            items, key=lambda i: i.published_at or datetime.min, reverse=True
        )
        prompt_items = sorted_items[:50]

        parts: list[str] = []
        for item in prompt_items:
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

            parts.append(f"{header}\n*{meta_line}*\n\n{body}")

        combined_text = "\n\n---\n\n".join(parts)

    return DailyIntakeContext(
        date=target_date,
        items=items,
        total_items=len(items),
        total_word_count=total_word_count,
        sources=sources,
        sites=sites,
        all_tags=tags,
        combined_text=combined_text,
    )
