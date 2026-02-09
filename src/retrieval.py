"""Similarity search at synthesis time — query the content store for related context."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distill.intake.models import ContentItem
    from distill.store import JsonStore, PgvectorStore

logger = logging.getLogger(__name__)


def _embeddings_available() -> bool:
    """Check if embeddings are available."""
    from distill.embeddings import is_available

    return is_available()


def _embed_text(text: str) -> list[float]:
    """Embed text using sentence-transformers."""
    from distill.embeddings import embed_text

    return embed_text(text)


def get_related_context(
    items: list[ContentItem],
    store: JsonStore | PgvectorStore,
    *,
    k: int = 5,
    query_text: str = "",
) -> str:
    """Find related past content and format it for LLM prompts.

    Builds a summary from current items, embeds it, queries the store
    for similar past content, and returns a formatted markdown section.

    Args:
        items: Current content items to find context for.
        store: Content store with embeddings.
        k: Number of similar items to retrieve.
        query_text: Optional custom query text. If empty, builds from items.

    Returns:
        Markdown string with related content, or empty string if unavailable.
    """
    if not _embeddings_available():
        return ""

    if not items and not query_text:
        return ""

    # Build query text from items if not provided
    if not query_text:
        query_text = _build_query_text(items)

    if not query_text:
        return ""

    try:
        embedding = _embed_text(query_text)
    except Exception:
        logger.warning("Failed to embed query text for retrieval", exc_info=True)
        return ""

    # Exclude current items from results
    exclude_ids = [item.id for item in items]

    try:
        similar = store.find_similar(embedding, k=k, exclude_ids=exclude_ids)
    except Exception:
        logger.warning("Similarity search failed", exc_info=True)
        return ""

    if not similar:
        return ""

    return _format_related_context(similar)


def get_related_context_for_topic(
    topic: str,
    store: JsonStore | PgvectorStore,
    *,
    k: int = 5,
) -> str:
    """Find related past content for a specific topic string.

    Convenience wrapper for blog synthesis where the query is a topic
    rather than a set of ContentItems.

    Args:
        topic: Topic or theme text to search for.
        store: Content store with embeddings.
        k: Number of similar items to retrieve.

    Returns:
        Markdown string with related content.
    """
    return get_related_context([], store, k=k, query_text=topic)


def _build_query_text(items: list[ContentItem]) -> str:
    """Build embeddable query text from a list of items."""
    parts: list[str] = []
    for item in items[:10]:  # Limit to avoid overly long queries
        if item.title:
            parts.append(item.title)
        if item.excerpt:
            parts.append(item.excerpt[:200])
    return " ".join(parts)[:1000]


def _format_related_context(items: list[ContentItem]) -> str:
    """Format retrieved items as a markdown section for prompts."""
    lines = ["## Related Past Content", ""]
    for item in items:
        date_str = ""
        if item.published_at:
            date_str = f" ({item.published_at.strftime('%Y-%m-%d')})"
        title = item.title or "Untitled"
        excerpt = ""
        if item.excerpt:
            excerpt = f" — {item.excerpt[:100]}..."
        elif item.body:
            excerpt = f" — {item.body[:100]}..."
        lines.append(f'- "{title}"{date_str}{excerpt}')
    lines.append("")
    return "\n".join(lines)
