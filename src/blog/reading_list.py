"""Reading list blog post type — curated weekly highlights from intake."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from distill.memory import UnifiedMemory
    from distill.store import JsonStore, PgvectorStore

logger = logging.getLogger(__name__)


class ReadingListContext(BaseModel):
    """Context for a reading list blog post."""

    week_start: date
    week_end: date
    items: list[dict[str, object]] = Field(default_factory=list)
    total_items_read: int = 0
    themes: list[str] = Field(default_factory=list)

    @property
    def year(self) -> int:
        return self.week_start.isocalendar().year

    @property
    def week(self) -> int:
        return self.week_start.isocalendar().week


def prepare_reading_list_context(
    output_dir: Path,
    year: int,
    week: int,
    unified_memory: UnifiedMemory,
    store: JsonStore | PgvectorStore,
    *,
    max_items: int = 10,
) -> ReadingListContext | None:
    """Build context for a reading list post from stored intake items.

    Queries the content store for intake items published during the
    given week, sorts by relevance classification, and picks the top items.

    Args:
        output_dir: Root output directory.
        year: ISO year.
        week: ISO week number.
        unified_memory: Memory for theme context.
        store: Content store to query.
        max_items: Maximum items to include.

    Returns:
        ReadingListContext if enough items found, else None.
    """
    # Calculate week date range
    week_start = date.fromisocalendar(year, week, 1)
    week_end = week_start + timedelta(days=6)

    try:
        items = store.find_by_date_range(week_start, week_end)
    except Exception:
        logger.warning("Failed to query store for reading list", exc_info=True)
        return None

    if not items:
        return None

    # Sort by relevance score from classification metadata
    scored_items: list[tuple[float, object]] = []
    for item in items:
        classification = item.metadata.get("classification", {})
        relevance = 0.5  # default
        if isinstance(classification, dict):
            relevance = classification.get("relevance", 0.5)
            if isinstance(relevance, str):
                try:
                    relevance = float(relevance)
                except ValueError:
                    relevance = 0.5
        scored_items.append((relevance, item))

    scored_items.sort(key=lambda x: x[0], reverse=True)
    top_items = scored_items[:max_items]

    # Build item dicts for the context
    context_items = []
    for score, item in top_items:
        context_items.append(
            {
                "title": item.title,
                "url": item.url,
                "author": item.author,
                "site": item.site_name,
                "excerpt": item.excerpt[:200] if item.excerpt else "",
                "tags": item.tags[:5],
                "relevance": score,
            }
        )

    # Collect themes from memory for the week
    themes: list[str] = []
    for entry in unified_memory.entries:
        if week_start <= entry.date <= week_end:
            themes.extend(entry.themes)
    themes = list(dict.fromkeys(themes))[:10]  # deduplicate, preserve order

    if not context_items:
        return None

    return ReadingListContext(
        week_start=week_start,
        week_end=week_end,
        items=context_items,
        total_items_read=len(items),
        themes=themes,
    )


def render_reading_list_prompt(context: ReadingListContext) -> str:
    """Render the reading list context as prompt text for the LLM."""
    lines = [
        f"# Reading List: Week {context.year}-W{context.week:02d}",
        f"({context.week_start.isoformat()} to {context.week_end.isoformat()})",
        "",
        f"Total articles read: {context.total_items_read}",
        f"Top {len(context.items)} curated below:",
        "",
    ]

    for i, item in enumerate(context.items, 1):
        title = item.get("title", "Untitled")
        author = item.get("author", "")
        site = item.get("site", "")
        excerpt = item.get("excerpt", "")
        tags: list[str] = item.get("tags", [])  # type: ignore[assignment]
        attribution = f" by {author}" if author else (f" ({site})" if site else "")

        lines.append(f"## {i}. {title}{attribution}")
        if excerpt:
            lines.append(f"> {excerpt}")
        if tags:
            lines.append(f"Tags: {', '.join(tags)}")
        lines.append("")

    if context.themes:
        lines.append(f"Weekly themes: {', '.join(context.themes)}")
        lines.append("")

    return "\n".join(lines)
