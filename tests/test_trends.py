"""Tests for src/trends.py — trend detection from UnifiedMemory."""

from datetime import date, timedelta

import pytest
from distill.memory import DailyEntry, EntityRecord, MemoryThread, UnifiedMemory
from distill.trends import Trend, _classify_direction, detect_trends, render_trends_for_prompt


@pytest.fixture
def memory_with_trends():
    """Create a memory with trending and declining topics."""
    today = date.today()
    entries = [
        DailyEntry(date=today - timedelta(days=i), themes=["rising-topic"])
        for i in range(5)
    ]
    # Add some old entries with a different topic
    entries.extend([
        DailyEntry(date=today - timedelta(days=i), themes=["old-topic"])
        for i in range(20, 25)
    ])
    return UnifiedMemory(entries=entries)


class TestDetectTrends:
    def test_empty_memory(self):
        memory = UnifiedMemory()
        trends = detect_trends(memory)
        assert trends == []

    def test_detects_rising_topic(self, memory_with_trends):
        trends = detect_trends(memory_with_trends, lookback_days=30, recent_days=7)
        names = [t.topic for t in trends]
        assert "rising-topic" in names
        rising = next(t for t in trends if t.topic == "rising-topic")
        assert rising.direction == "rising"

    def test_detects_declining_topic(self, memory_with_trends):
        trends = detect_trends(memory_with_trends, lookback_days=30, recent_days=7)
        names = [t.topic for t in trends]
        assert "old-topic" in names
        old = next(t for t in trends if t.topic == "old-topic")
        assert old.direction == "declining"

    def test_includes_entity_trends(self):
        today = date.today()
        memory = UnifiedMemory(
            entries=[DailyEntry(date=today)],
            entities={
                "project:distill": EntityRecord(
                    name="distill",
                    entity_type="project",
                    first_seen=today - timedelta(days=10),
                    last_seen=today,
                    mention_count=10,
                ),
            },
        )
        trends = detect_trends(memory)
        names = [t.topic for t in trends]
        assert "distill" in names

    def test_filters_low_count_topics(self):
        today = date.today()
        memory = UnifiedMemory(
            entries=[DailyEntry(date=today, themes=["one-off"])],
        )
        trends = detect_trends(memory)
        # "one-off" has count 1, below threshold of 2
        assert all(t.topic != "one-off" for t in trends)

    def test_sorted_by_recent_count(self):
        today = date.today()
        entries = [
            DailyEntry(date=today, themes=["a", "b", "b"]),
            DailyEntry(date=today - timedelta(days=1), themes=["b"]),
        ]
        memory = UnifiedMemory(entries=entries)
        trends = detect_trends(memory, lookback_days=30, recent_days=7)
        if len(trends) >= 2:
            assert trends[0].recent_count >= trends[1].recent_count


class TestClassifyDirection:
    def test_rising(self):
        assert _classify_direction(10, 8, 30, 7) == "rising"

    def test_declining(self):
        assert _classify_direction(10, 0, 30, 7) == "declining"

    def test_stable(self):
        assert _classify_direction(10, 2, 30, 7) == "stable"

    def test_zero_total(self):
        assert _classify_direction(0, 0, 30, 7) == "stable"


class TestRenderTrends:
    def test_empty(self):
        assert render_trends_for_prompt([]) == ""

    def test_basic_render(self):
        trends = [
            Trend(topic="AI agents", direction="rising", mention_count=10, recent_count=7),
            Trend(topic="testing", direction="stable", mention_count=5, recent_count=2),
        ]
        text = render_trends_for_prompt(trends)
        assert "## Trending Topics" in text
        assert "AI agents (rising, 7x this week)" in text
        assert "testing (stable, 2x this week)" in text

    def test_max_trends_limit(self):
        trends = [
            Trend(topic=f"topic-{i}", direction="rising", recent_count=i)
            for i in range(10)
        ]
        text = render_trends_for_prompt(trends, max_trends=3)
        lines = [l for l in text.strip().split("\n") if l.startswith("- ")]
        assert len(lines) == 3

    def test_includes_related_entities(self):
        trends = [
            Trend(
                topic="AI",
                direction="rising",
                recent_count=5,
                related_entities=["Claude", "GPT"],
            )
        ]
        text = render_trends_for_prompt(trends)
        assert "related: Claude, GPT" in text
