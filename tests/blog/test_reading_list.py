"""Tests for src/blog/reading_list.py — reading list blog post type."""

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from distill.blog.reading_list import (
    ReadingListContext,
    prepare_reading_list_context,
    render_reading_list_prompt,
)
from distill.memory import DailyEntry, UnifiedMemory


@pytest.fixture
def mock_store():
    """Create a mock content store with items."""
    store = MagicMock()

    # Create mock items
    items = []
    for i in range(5):
        item = MagicMock()
        item.title = f"Article {i}"
        item.url = f"https://example.com/{i}"
        item.author = f"Author {i}"
        item.site_name = f"Site {i}"
        item.excerpt = f"Excerpt for article {i}"
        item.tags = ["ai", "engineering"]
        item.metadata = {
            "classification": {"relevance": 0.9 - i * 0.1}
        }
        items.append(item)

    store.find_by_date_range.return_value = items
    return store


@pytest.fixture
def unified_memory():
    """Create a unified memory with weekly entries."""
    today = date.today()
    iso = today.isocalendar()
    week_start = date.fromisocalendar(iso.year, iso.week, 1)
    return UnifiedMemory(
        entries=[
            DailyEntry(
                date=week_start,
                themes=["content-pipeline", "ai-agents"],
            ),
            DailyEntry(
                date=week_start + timedelta(days=1),
                themes=["testing", "ai-agents"],
            ),
        ]
    )


class TestReadingListContext:
    def test_week_properties(self):
        ctx = ReadingListContext(
            week_start=date(2026, 2, 2),
            week_end=date(2026, 2, 8),
        )
        assert ctx.year == 2026
        assert ctx.week == 6

    def test_empty_items(self):
        ctx = ReadingListContext(
            week_start=date(2026, 2, 2),
            week_end=date(2026, 2, 8),
        )
        assert ctx.items == []
        assert ctx.total_items_read == 0


class TestPrepareReadingListContext:
    def test_returns_context_with_items(self, tmp_path, mock_store, unified_memory):
        today = date.today()
        iso = today.isocalendar()
        ctx = prepare_reading_list_context(
            tmp_path, iso.year, iso.week, unified_memory, mock_store
        )
        assert ctx is not None
        assert len(ctx.items) == 5
        assert ctx.total_items_read == 5

    def test_returns_none_when_no_items(self, tmp_path, unified_memory):
        store = MagicMock()
        store.find_by_date_range.return_value = []
        ctx = prepare_reading_list_context(
            tmp_path, 2026, 6, unified_memory, store
        )
        assert ctx is None

    def test_sorts_by_relevance(self, tmp_path, mock_store, unified_memory):
        today = date.today()
        iso = today.isocalendar()
        ctx = prepare_reading_list_context(
            tmp_path, iso.year, iso.week, unified_memory, mock_store
        )
        assert ctx is not None
        # First item should have highest relevance
        assert ctx.items[0]["relevance"] >= ctx.items[-1]["relevance"]

    def test_limits_max_items(self, tmp_path, unified_memory):
        store = MagicMock()
        items = []
        for i in range(20):
            item = MagicMock()
            item.title = f"Article {i}"
            item.url = f"https://example.com/{i}"
            item.author = ""
            item.site_name = ""
            item.excerpt = ""
            item.tags = []
            item.metadata = {"classification": {"relevance": 0.5}}
            items.append(item)
        store.find_by_date_range.return_value = items

        today = date.today()
        iso = today.isocalendar()
        ctx = prepare_reading_list_context(
            tmp_path, iso.year, iso.week, unified_memory, store, max_items=5
        )
        assert ctx is not None
        assert len(ctx.items) == 5
        assert ctx.total_items_read == 20

    def test_collects_themes_from_memory(self, tmp_path, mock_store, unified_memory):
        today = date.today()
        iso = today.isocalendar()
        ctx = prepare_reading_list_context(
            tmp_path, iso.year, iso.week, unified_memory, mock_store
        )
        assert ctx is not None
        assert "ai-agents" in ctx.themes

    def test_handles_store_error(self, tmp_path, unified_memory):
        store = MagicMock()
        store.find_by_date_range.side_effect = RuntimeError("db error")
        ctx = prepare_reading_list_context(
            tmp_path, 2026, 6, unified_memory, store
        )
        assert ctx is None


class TestRenderReadingListPrompt:
    def test_renders_basic_prompt(self):
        ctx = ReadingListContext(
            week_start=date(2026, 2, 2),
            week_end=date(2026, 2, 8),
            items=[
                {
                    "title": "Great Article",
                    "url": "https://example.com/1",
                    "author": "John",
                    "site": "Blog",
                    "excerpt": "An excerpt",
                    "tags": ["ai"],
                    "relevance": 0.9,
                },
            ],
            total_items_read=10,
            themes=["AI", "testing"],
        )
        text = render_reading_list_prompt(ctx)
        assert "Reading List: Week 2026-W06" in text
        assert "Great Article" in text
        assert "by John" in text
        assert "Total articles read: 10" in text
        assert "Weekly themes: AI, testing" in text

    def test_empty_items(self):
        ctx = ReadingListContext(
            week_start=date(2026, 2, 2),
            week_end=date(2026, 2, 8),
        )
        text = render_reading_list_prompt(ctx)
        assert "Top 0 curated below" in text
