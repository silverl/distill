"""Trend detection from UnifiedMemory entity and thread data."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from distill.memory import UnifiedMemory
from pydantic import BaseModel, Field


class Trend(BaseModel):
    """A detected trend in topics or entities."""

    topic: str
    direction: str  # "rising", "stable", "declining"
    mention_count: int = 0
    recent_count: int = 0
    related_entities: list[str] = Field(default_factory=list)


def detect_trends(
    memory: UnifiedMemory,
    lookback_days: int = 30,
    recent_days: int = 7,
) -> list[Trend]:
    """Detect trending topics from memory entries and entities.

    Compares mention frequency in the recent window vs the overall window
    to classify topics as rising, stable, or declining.

    Args:
        memory: The unified memory with entries, threads, and entities.
        lookback_days: Total window to consider.
        recent_days: Recent window for trend comparison.

    Returns:
        List of detected trends, sorted by recent_count descending.
    """
    if not memory.entries:
        return []

    latest = max(e.date for e in memory.entries)
    lookback_cutoff = latest - timedelta(days=lookback_days)
    recent_cutoff = latest - timedelta(days=recent_days)

    # Count theme mentions across all entries
    all_themes: Counter[str] = Counter()
    recent_themes: Counter[str] = Counter()

    for entry in memory.entries:
        if entry.date < lookback_cutoff:
            continue
        for theme in entry.themes:
            all_themes[theme] += 1
            if entry.date >= recent_cutoff:
                recent_themes[theme] += 1

    # Also count entity mentions
    entity_counts: Counter[str] = Counter()
    recent_entity_counts: Counter[str] = Counter()
    entity_types: dict[str, str] = {}

    for _key, entity in memory.entities.items():
        if entity.last_seen < lookback_cutoff:
            continue
        entity_counts[entity.name] += entity.mention_count
        entity_types[entity.name] = entity.entity_type
        if entity.last_seen >= recent_cutoff:
            recent_entity_counts[entity.name] += entity.mention_count

    # Build entity relationships: entities that share themes with a topic
    topic_entities: dict[str, list[str]] = {}
    for entry in memory.entries:
        entry_entities = []
        for _key, entity in memory.entities.items():
            if entity.last_seen == entry.date:
                entry_entities.append(entity.name)
        for theme in entry.themes:
            if theme not in topic_entities:
                topic_entities[theme] = []
            topic_entities[theme].extend(entry_entities)

    # Merge themes and entities into trend candidates
    all_topics = set(all_themes.keys()) | set(entity_counts.keys())

    trends: list[Trend] = []
    for topic in all_topics:
        total = all_themes.get(topic, 0) + entity_counts.get(topic, 0)
        recent = recent_themes.get(topic, 0) + recent_entity_counts.get(topic, 0)

        if total < 2:
            continue  # Not enough data

        direction = _classify_direction(total, recent, lookback_days, recent_days)

        related = list(set(topic_entities.get(topic, [])))[:5]

        trends.append(
            Trend(
                topic=topic,
                direction=direction,
                mention_count=total,
                recent_count=recent,
                related_entities=related,
            )
        )

    trends.sort(key=lambda t: t.recent_count, reverse=True)
    return trends


def _classify_direction(
    total: int,
    recent: int,
    lookback_days: int,
    recent_days: int,
) -> str:
    """Classify a trend direction based on frequency ratios."""
    if total == 0:
        return "stable"

    # Expected recent count if evenly distributed
    expected_ratio = recent_days / lookback_days
    expected = total * expected_ratio

    if expected < 1:
        expected = 1

    ratio = recent / expected if expected > 0 else 0

    if ratio >= 1.5:
        return "rising"
    elif ratio <= 0.5:
        return "declining"
    return "stable"


def render_trends_for_prompt(trends: list[Trend], max_trends: int = 5) -> str:
    """Render trends as a markdown section for LLM prompts.

    Args:
        trends: Detected trends.
        max_trends: Maximum number of trends to include.

    Returns:
        Markdown string or empty string if no trends.
    """
    if not trends:
        return ""

    lines = ["## Trending Topics", ""]
    for trend in trends[:max_trends]:
        related = ""
        if trend.related_entities:
            related = f" (related: {', '.join(trend.related_entities[:3])})"
        lines.append(
            f"- {trend.topic} ({trend.direction}, {trend.recent_count}x this week){related}"
        )
    lines.append("")
    return "\n".join(lines)
