"""Tests for unified intake context — sessions + content + seeds."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from distill.intake.context import (
    DailyIntakeContext,
    _render_content_section,
    _render_seed_section,
    _render_session_section,
    prepare_daily_context,
)
from distill.intake.models import ContentItem, ContentSource, ContentType


def _make_item(
    source: ContentSource = ContentSource.RSS,
    title: str = "Test Article",
    body: str = "Article body text.",
    **kwargs,
) -> ContentItem:
    return ContentItem(
        id=f"item-{hash(title) % 10000}",
        title=title,
        body=body,
        source=source,
        content_type=ContentType.ARTICLE,
        **kwargs,
    )


def _make_session_item(title: str = "Built auth", **kwargs) -> ContentItem:
    return _make_item(
        source=ContentSource.SESSION,
        title=title,
        body="Implemented authentication module.",
        site_name="claude",
        metadata={
            "project": "my-project",
            "duration_minutes": 30.0,
            "tools_used": [{"name": "Read", "count": 10}, {"name": "Edit", "count": 5}],
        },
        **kwargs,
    )


def _make_seed_item(title: str = "AI agents as APIs", **kwargs) -> ContentItem:
    return _make_item(
        source=ContentSource.SEEDS,
        title=title,
        body=title,
        tags=["ai", "agents"],
        metadata={"seed_id": "s123", "seed_type": "idea"},
        **kwargs,
    )


class TestContextPartitioning:
    """Test that items are correctly partitioned by source type."""

    def test_sessions_partitioned(self):
        items = [_make_session_item(), _make_item()]
        ctx = prepare_daily_context(items)
        assert len(ctx.session_items) == 1
        assert len(ctx.content_items) == 1

    def test_seeds_partitioned(self):
        items = [_make_seed_item(), _make_item()]
        ctx = prepare_daily_context(items)
        assert len(ctx.seed_items) == 1
        assert len(ctx.content_items) == 1

    def test_all_three_types(self):
        items = [_make_session_item(), _make_seed_item(), _make_item()]
        ctx = prepare_daily_context(items)
        assert len(ctx.session_items) == 1
        assert len(ctx.seed_items) == 1
        assert len(ctx.content_items) == 1
        assert ctx.total_items == 3

    def test_content_only(self):
        items = [_make_item(), _make_item(title="Other")]
        ctx = prepare_daily_context(items)
        assert len(ctx.session_items) == 0
        assert len(ctx.seed_items) == 0
        assert len(ctx.content_items) == 2

    def test_has_sessions_property(self):
        ctx = prepare_daily_context([_make_session_item()])
        assert ctx.has_sessions is True

    def test_no_sessions_property(self):
        ctx = prepare_daily_context([_make_item()])
        assert ctx.has_sessions is False

    def test_has_seeds_property(self):
        ctx = prepare_daily_context([_make_seed_item()])
        assert ctx.has_seeds is True


class TestProjectToolAggregation:
    """Test aggregation of projects and tools from session metadata."""

    def test_projects_extracted(self):
        items = [
            _make_session_item(),
            _make_item(
                source=ContentSource.SESSION,
                title="Session 2",
                metadata={"project": "other-project"},
            ),
        ]
        ctx = prepare_daily_context(items)
        assert "my-project" in ctx.projects_worked_on
        assert "other-project" in ctx.projects_worked_on

    def test_projects_deduped(self):
        items = [
            _make_session_item(),
            _make_item(
                source=ContentSource.SESSION,
                title="Session 2",
                metadata={"project": "my-project"},
            ),
        ]
        ctx = prepare_daily_context(items)
        assert ctx.projects_worked_on.count("my-project") == 1

    def test_tools_extracted(self):
        items = [_make_session_item()]
        ctx = prepare_daily_context(items)
        assert "Read" in ctx.tools_used_today
        assert "Edit" in ctx.tools_used_today

    def test_no_session_metadata(self):
        items = [_make_item()]
        ctx = prepare_daily_context(items)
        assert ctx.projects_worked_on == []
        assert ctx.tools_used_today == []


class TestCombinedText:
    """Test combined text rendering."""

    def test_sessions_in_combined_text(self):
        items = [_make_session_item()]
        ctx = prepare_daily_context(items)
        assert "What You Built Today" in ctx.combined_text

    def test_seeds_in_combined_text(self):
        items = [_make_seed_item()]
        ctx = prepare_daily_context(items)
        assert "What You're Thinking About" in ctx.combined_text

    def test_content_in_combined_text(self):
        items = [_make_item(title="Great Article")]
        ctx = prepare_daily_context(items)
        assert "What You Read Today" in ctx.combined_text

    def test_all_sections_present(self):
        items = [_make_session_item(), _make_seed_item(), _make_item()]
        ctx = prepare_daily_context(items)
        assert "What You Built Today" in ctx.combined_text
        assert "What You're Thinking About" in ctx.combined_text
        assert "What You Read Today" in ctx.combined_text

    def test_content_only_uses_clustered_text(self):
        items = [_make_item()]
        ctx = prepare_daily_context(items, clustered_text="## Clustered content here")
        assert ctx.combined_text == "## Clustered content here"

    def test_mixed_with_clustered_text(self):
        """When sessions present, clustered text goes under 'What You Read'."""
        items = [_make_session_item(), _make_item()]
        ctx = prepare_daily_context(items, clustered_text="## Clustered")
        assert "What You Built Today" in ctx.combined_text
        assert "Clustered" in ctx.combined_text


class TestRenderSections:
    """Test section rendering functions."""

    def test_render_session_section(self):
        items = [_make_session_item()]
        result = _render_session_section(items)
        assert "What You Built Today" in result
        assert "Built auth" in result
        assert "Project: my-project" in result
        assert "Duration: 30.0min" in result

    def test_render_session_empty(self):
        assert _render_session_section([]) == ""

    def test_render_seed_section(self):
        items = [_make_seed_item()]
        result = _render_seed_section(items)
        assert "What You're Thinking About" in result
        assert "AI agents as APIs" in result
        assert "[ai, agents]" in result

    def test_render_seed_empty(self):
        assert _render_seed_section([]) == ""

    def test_render_content_section(self):
        items = [_make_item(title="Great Read")]
        result = _render_content_section(items)
        assert "What You Read Today" in result
        assert "Great Read" in result

    def test_render_content_empty(self):
        assert _render_content_section([]) == ""


class TestBackwardCompatibility:
    """Ensure existing content-only intake still works."""

    def test_content_only_context(self):
        items = [_make_item(title="Article 1"), _make_item(title="Article 2")]
        ctx = prepare_daily_context(items)
        assert ctx.total_items == 2
        assert "rss" in ctx.sources
        assert ctx.session_items == []
        assert ctx.seed_items == []
