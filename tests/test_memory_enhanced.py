"""Tests for enhanced UnifiedMemory.render_for_prompt with entities and trends."""

from datetime import date, timedelta

import pytest
from distill.memory import (
    DailyEntry,
    EntityRecord,
    MemoryThread,
    PublishedRecord,
    UnifiedMemory,
)


class TestRenderForPromptEntities:
    def test_includes_entity_section(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
            entities={
                "project:distill": EntityRecord(
                    name="distill",
                    entity_type="project",
                    first_seen=date.today() - timedelta(days=20),
                    last_seen=date.today(),
                    mention_count=15,
                ),
                "tech:pgvector": EntityRecord(
                    name="pgvector",
                    entity_type="technology",
                    first_seen=date.today() - timedelta(days=13),
                    last_seen=date.today(),
                    mention_count=8,
                ),
            },
        )
        text = memory.render_for_prompt()
        assert "## What You've Been Working On" in text
        assert "**distill** (project): 15x over" in text
        assert "**pgvector** (technology): 8x over" in text

    def test_sorts_by_mention_count(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
            entities={
                "a:low": EntityRecord(
                    name="low",
                    entity_type="a",
                    first_seen=date.today(),
                    last_seen=date.today(),
                    mention_count=1,
                ),
                "b:high": EntityRecord(
                    name="high",
                    entity_type="b",
                    first_seen=date.today(),
                    last_seen=date.today(),
                    mention_count=10,
                ),
            },
        )
        text = memory.render_for_prompt()
        # "high" should appear before "low"
        assert text.index("high") < text.index("low")

    def test_limits_to_10_entities(self):
        entities = {}
        for i in range(15):
            entities[f"type:entity-{i}"] = EntityRecord(
                name=f"entity-{i}",
                entity_type="type",
                first_seen=date.today(),
                last_seen=date.today(),
                mention_count=i + 1,
            )
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
            entities=entities,
        )
        text = memory.render_for_prompt()
        # Count entity lines
        entity_lines = [l for l in text.split("\n") if l.startswith("- **")]
        # Thread lines could also match, but entity section should be <= 10
        assert len(entity_lines) <= 10

    def test_no_entity_section_when_empty(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
        )
        text = memory.render_for_prompt()
        assert "## What You've Been Working On" not in text


class TestRenderForPromptTrends:
    def test_includes_injected_trends(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
        )
        memory.inject_trends("## Trending Topics\n- AI (rising, 5x)")
        text = memory.render_for_prompt()
        assert "## Trending Topics" in text
        assert "AI (rising, 5x)" in text

    def test_no_trends_by_default(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
        )
        text = memory.render_for_prompt()
        assert "Trending" not in text


class TestRenderForPromptFocus:
    def test_sessions_focus_excludes_reads(self):
        memory = UnifiedMemory(
            entries=[
                DailyEntry(
                    date=date.today(),
                    sessions=["Built parser"],
                    reads=["Read about ML"],
                ),
            ],
        )
        text = memory.render_for_prompt(focus="sessions")
        assert "Built parser" in text
        assert "Read about ML" not in text

    def test_intake_focus_excludes_sessions(self):
        memory = UnifiedMemory(
            entries=[
                DailyEntry(
                    date=date.today(),
                    sessions=["Built parser"],
                    reads=["Read about ML"],
                ),
            ],
        )
        text = memory.render_for_prompt(focus="intake")
        assert "Read about ML" in text
        assert "Built parser" not in text

    def test_blog_focus_includes_published(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
            published=[
                PublishedRecord(
                    slug="weekly-2026-W06",
                    title="Week 6 Roundup",
                    post_type="weekly",
                    date=date.today(),
                    platforms=["obsidian"],
                ),
            ],
        )
        text = memory.render_for_prompt(focus="blog")
        assert "## Recently Published" in text
        assert "Week 6 Roundup" in text

    def test_sessions_focus_excludes_published(self):
        memory = UnifiedMemory(
            entries=[DailyEntry(date=date.today())],
            published=[
                PublishedRecord(
                    slug="weekly-2026-W06",
                    title="Week 6",
                    post_type="weekly",
                    date=date.today(),
                ),
            ],
        )
        text = memory.render_for_prompt(focus="sessions")
        assert "Recently Published" not in text


class TestRenderForPromptComplete:
    def test_full_render_with_all_sections(self):
        memory = UnifiedMemory(
            entries=[
                DailyEntry(
                    date=date.today(),
                    sessions=["Built intake pipeline"],
                    reads=["Read about embeddings"],
                    themes=["content-pipeline"],
                    insights=["Embeddings improve search"],
                    decisions=["Use MiniLM model"],
                    open_questions=["How to handle duplicates?"],
                ),
            ],
            threads=[
                MemoryThread(
                    name="content pipeline",
                    summary="Building end-to-end pipeline",
                    first_seen=date.today() - timedelta(days=10),
                    last_seen=date.today(),
                    mention_count=5,
                    status="active",
                ),
            ],
            entities={
                "project:distill": EntityRecord(
                    name="distill",
                    entity_type="project",
                    first_seen=date.today() - timedelta(days=20),
                    last_seen=date.today(),
                    mention_count=15,
                ),
            },
            published=[
                PublishedRecord(
                    slug="weekly-1",
                    title="Week 1",
                    post_type="weekly",
                    date=date.today(),
                    platforms=["obsidian"],
                ),
            ],
        )
        text = memory.render_for_prompt()
        assert "# Memory Context" in text
        assert "Sessions:" in text
        assert "Reads:" in text
        assert "Themes:" in text
        assert "Insights:" in text
        assert "Decisions:" in text
        assert "Open questions:" in text
        assert "## Ongoing Threads" in text
        assert "## What You've Been Working On" in text
        assert "## Recently Published" in text
