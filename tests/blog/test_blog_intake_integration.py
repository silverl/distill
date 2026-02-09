"""Tests for blog integration with intake digests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from distill.blog.context import prepare_thematic_context, prepare_weekly_context
from distill.blog.prompts import get_blog_prompt
from distill.blog.reader import IntakeDigestEntry, JournalEntry, JournalReader
from distill.blog.config import BlogPostType
from distill.blog.themes import ThemeDefinition


def _make_journal_entry(
    entry_date: date = date(2026, 2, 3),
    prose: str = "Worked on session parser today.",
    projects: list[str] | None = None,
) -> JournalEntry:
    return JournalEntry(
        date=entry_date,
        sessions_count=3,
        duration_minutes=120.0,
        tags=["coding", "python"],
        projects=projects or ["distill"],
        prose=prose,
    )


def _make_intake_digest(
    entry_date: date = date(2026, 2, 3),
    prose: str = "Read about AI agents and testing patterns.",
    themes: list[str] | None = None,
) -> IntakeDigestEntry:
    return IntakeDigestEntry(
        date=entry_date,
        themes=themes or ["AI agents", "testing"],
        prose=prose,
    )


class TestJournalReaderIntake:
    """Test reading intake digests via JournalReader."""

    def test_read_intake_digests(self, tmp_path):
        intake_dir = tmp_path / "intake"
        intake_dir.mkdir()

        # Write a fake intake digest
        content = """---
date: 2026-02-03
themes:
  - AI agents
  - testing
---

# Daily Intake Digest

Read about AI agents today.
"""
        (intake_dir / "intake-2026-02-03-obsidian.md").write_text(content)

        reader = JournalReader()
        digests = reader.read_intake_digests(intake_dir)

        assert len(digests) == 1
        assert digests[0].date == date(2026, 2, 3)
        assert "AI agents" in digests[0].themes

    def test_read_intake_empty_dir(self, tmp_path):
        reader = JournalReader()
        digests = reader.read_intake_digests(tmp_path / "nonexistent")
        assert digests == []

    def test_read_intake_extracts_prose(self, tmp_path):
        intake_dir = tmp_path / "intake"
        intake_dir.mkdir()

        content = """---
date: 2026-02-03
---

# Daily Digest

This is the prose content about what I read.
"""
        (intake_dir / "intake-2026-02-03-obsidian.md").write_text(content)

        reader = JournalReader()
        digests = reader.read_intake_digests(intake_dir)

        assert "prose content" in digests[0].prose

    def test_read_intake_date_from_filename(self, tmp_path):
        intake_dir = tmp_path / "intake"
        intake_dir.mkdir()

        content = "# Digest\n\nContent here."
        (intake_dir / "intake-2026-02-05-obsidian.md").write_text(content)

        reader = JournalReader()
        digests = reader.read_intake_digests(intake_dir)

        assert len(digests) == 1
        assert digests[0].date == date(2026, 2, 5)


class TestWeeklyContextWithIntake:
    """Test weekly blog context with intake digests."""

    def test_context_includes_intake(self):
        entries = [
            _make_journal_entry(date(2026, 2, 2)),
            _make_journal_entry(date(2026, 2, 3)),
        ]
        digests = [
            _make_intake_digest(date(2026, 2, 2), "AI article summary"),
            _make_intake_digest(date(2026, 2, 3), "Testing article"),
        ]

        ctx = prepare_weekly_context(entries, 2026, 6, intake_digests=digests)

        assert "What You Read This Week" in ctx.intake_context
        assert "AI article summary" in ctx.intake_context

    def test_context_reading_themes(self):
        entries = [_make_journal_entry(date(2026, 2, 2))]
        digests = [
            _make_intake_digest(date(2026, 2, 2), themes=["AI agents"]),
            _make_intake_digest(date(2026, 2, 3), themes=["testing"]),
        ]

        ctx = prepare_weekly_context(entries, 2026, 6, intake_digests=digests)

        assert "AI agents" in ctx.reading_themes
        assert "testing" in ctx.reading_themes

    def test_context_without_intake(self):
        entries = [_make_journal_entry(date(2026, 2, 2))]
        ctx = prepare_weekly_context(entries, 2026, 6)

        assert ctx.intake_context == ""
        assert ctx.reading_themes == []

    def test_context_filters_digests_to_week(self):
        entries = [_make_journal_entry(date(2026, 2, 2))]
        # Digest from a different week
        digests = [_make_intake_digest(date(2026, 1, 15))]

        ctx = prepare_weekly_context(entries, 2026, 6, intake_digests=digests)
        assert ctx.intake_context == ""

    def test_context_dedupes_themes(self):
        entries = [_make_journal_entry(date(2026, 2, 2))]
        digests = [
            _make_intake_digest(date(2026, 2, 2), themes=["AI"]),
            _make_intake_digest(date(2026, 2, 3), themes=["AI", "testing"]),
        ]

        ctx = prepare_weekly_context(entries, 2026, 6, intake_digests=digests)
        assert ctx.reading_themes.count("AI") == 1


class TestThematicContextWithIntake:
    """Test thematic blog context with intake digests."""

    def test_thematic_includes_intake(self):
        theme = ThemeDefinition(
            slug="testing-patterns",
            title="Testing Patterns",
            description="How testing patterns evolve.",
            keywords=["testing", "patterns"],
            min_evidence=1,
            thread_patterns=["testing"],
        )
        evidence = [_make_journal_entry(date(2026, 2, 3))]
        digests = [
            _make_intake_digest(date(2026, 2, 3), "Related reading about testing"),
        ]

        ctx = prepare_thematic_context(theme, evidence, intake_digests=digests)
        assert "Related Reading" in ctx.intake_context
        assert "testing" in ctx.intake_context

    def test_thematic_without_intake(self):
        theme = ThemeDefinition(
            slug="testing-patterns",
            title="Testing Patterns",
            description="How testing patterns evolve.",
            keywords=["testing"],
            min_evidence=1,
            thread_patterns=[],
        )
        evidence = [_make_journal_entry(date(2026, 2, 3))]
        ctx = prepare_thematic_context(theme, evidence)
        assert ctx.intake_context == ""


class TestBlogPromptWithIntake:
    """Test blog prompts include intake context."""

    def test_weekly_prompt_with_intake(self):
        prompt = get_blog_prompt(
            BlogPostType.WEEKLY,
            word_count=1200,
            intake_context="## AI agents article summary",
        )
        assert "What You Read" in prompt
        assert "AI agents article summary" in prompt

    def test_weekly_prompt_without_intake(self):
        prompt = get_blog_prompt(BlogPostType.WEEKLY, word_count=1200)
        assert "What You Read" not in prompt

    def test_thematic_prompt_with_intake(self):
        prompt = get_blog_prompt(
            BlogPostType.THEMATIC,
            word_count=1200,
            theme_title="Testing Patterns",
            intake_context="## Testing articles",
        )
        assert "What You Read" in prompt
        assert "Testing articles" in prompt


class TestBackwardCompatibility:
    """Ensure blog works without intake."""

    def test_weekly_context_no_intake(self):
        entries = [
            _make_journal_entry(date(2026, 2, 2)),
            _make_journal_entry(date(2026, 2, 3)),
        ]
        ctx = prepare_weekly_context(entries, 2026, 6)
        assert ctx.total_sessions > 0
        assert ctx.intake_context == ""
        assert ctx.reading_themes == []

    def test_prompt_no_intake(self):
        prompt = get_blog_prompt(BlogPostType.WEEKLY, word_count=1200)
        assert "weekly synthesis" in prompt.lower() or "weekly" in prompt.lower()
