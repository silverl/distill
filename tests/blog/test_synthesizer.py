"""Tests for blog synthesizer (mocked subprocess)."""

import subprocess
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from distill.blog.config import BlogConfig
from distill.blog.context import ThematicBlogContext, WeeklyBlogContext
from distill.blog.reader import JournalEntry
from distill.blog.synthesizer import BlogSynthesisError, BlogSynthesizer
from distill.blog.themes import ThemeDefinition


def _make_weekly_context() -> WeeklyBlogContext:
    return WeeklyBlogContext(
        year=2026,
        week=6,
        week_start=date(2026, 2, 2),
        week_end=date(2026, 2, 8),
        entries=[
            JournalEntry(date=date(2026, 2, 3), prose="Monday work."),
            JournalEntry(date=date(2026, 2, 5), prose="Wednesday work."),
        ],
        total_sessions=10,
        total_duration_minutes=200,
        projects=["vermas"],
        combined_prose="Combined prose here.",
    )


def _make_thematic_context() -> ThematicBlogContext:
    return ThematicBlogContext(
        theme=ThemeDefinition(
            slug="test-theme",
            title="Test Theme Title",
            keywords=["test"],
            thread_patterns=[],
        ),
        evidence_entries=[
            JournalEntry(date=date(2026, 2, 3), prose="Evidence."),
        ],
        date_range=(date(2026, 2, 1), date(2026, 2, 5)),
        evidence_count=1,
        combined_evidence="Combined evidence here.",
    )


class TestBlogSynthesizer:
    @patch("distill.blog.synthesizer.subprocess.run")
    def test_weekly_synthesis(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Week in Review\n\nGreat week of progress...",
            stderr="",
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        result = synthesizer.synthesize_weekly(_make_weekly_context())

        assert "Week in Review" in result
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert cmd[1] == "-p"

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_thematic_synthesis(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Deep Dive\n\nExploring the theme...",
            stderr="",
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        result = synthesizer.synthesize_thematic(_make_thematic_context())

        assert "Deep Dive" in result
        mock_run.assert_called_once()

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_passes_model_flag(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Prose", stderr=""
        )
        config = BlogConfig(model="claude-sonnet-4-5-20250929")
        synthesizer = BlogSynthesizer(config)
        synthesizer.synthesize_weekly(_make_weekly_context())

        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "claude-sonnet-4-5-20250929" in cmd

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_no_model_flag_by_default(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Prose", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        synthesizer.synthesize_weekly(_make_weekly_context())

        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_cli_not_found(self, mock_run: MagicMock):
        mock_run.side_effect = FileNotFoundError()
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)

        with pytest.raises(BlogSynthesisError, match="not found"):
            synthesizer.synthesize_weekly(_make_weekly_context())

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_cli_timeout(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=180)
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)

        with pytest.raises(BlogSynthesisError, match="timed out"):
            synthesizer.synthesize_weekly(_make_weekly_context())

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_cli_nonzero_exit(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="API error"
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)

        with pytest.raises(BlogSynthesisError, match="exited 1"):
            synthesizer.synthesize_thematic(_make_thematic_context())

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_uses_configured_timeout(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="prose", stderr=""
        )
        config = BlogConfig(claude_timeout=300)
        synthesizer = BlogSynthesizer(config)
        synthesizer.synthesize_weekly(_make_weekly_context())

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_adapt_for_platform_calls_claude_with_social_prompt(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="1/ Great thread hook...", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        synthesizer.adapt_for_platform("Blog prose here", "twitter", "weekly-W06")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        prompt_arg = cmd[-1]
        assert "Twitter/X thread" in prompt_arg

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_adapt_for_platform_returns_output(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="1/ Hook tweet\n2/ Detail tweet", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        result = synthesizer.adapt_for_platform("Blog prose", "twitter", "weekly-W06")

        assert "1/ Hook tweet" in result

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_extract_blog_memory_parses_json(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"key_points": ["point 1", "point 2"], "themes_covered": ["agents"]}',
            stderr="",
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        summary = synthesizer.extract_blog_memory(
            "Blog prose", "weekly-W06", "Week 6 Post", "weekly"
        )

        assert summary.slug == "weekly-W06"
        assert summary.title == "Week 6 Post"
        assert summary.post_type == "weekly"
        assert summary.key_points == ["point 1", "point 2"]
        assert summary.themes_covered == ["agents"]
        assert summary.platforms_published == []

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_extract_blog_memory_handles_bad_json(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="not valid json at all", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        summary = synthesizer.extract_blog_memory(
            "Blog prose", "weekly-W06", "Week 6 Post", "weekly"
        )

        assert summary.slug == "weekly-W06"
        assert summary.key_points == []
        assert summary.themes_covered == []

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_synthesize_weekly_with_blog_memory(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="# Post with memory", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        memory_text = "## Previous Blog Posts\n\n- Some older post"
        result = synthesizer.synthesize_weekly(
            _make_weekly_context(), blog_memory=memory_text
        )

        assert "Post with memory" in result
        cmd = mock_run.call_args[0][0]
        prompt_arg = cmd[-1]
        assert "Previous Blog Posts" in prompt_arg

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_weekly_prompt_includes_project_context(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="# Post", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        ctx = _make_weekly_context()
        ctx.project_context = "## Project Context\n\n**VerMAS**: Multi-agent platform"
        synthesizer.synthesize_weekly(ctx)

        cmd = mock_run.call_args[0][0]
        prompt_arg = cmd[-1]
        assert "**VerMAS**: Multi-agent platform" in prompt_arg

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_weekly_prompt_includes_editorial_notes(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="# Post", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        ctx = _make_weekly_context()
        ctx.editorial_notes = "## Editorial Direction\n\n- Focus on fan-in pattern"
        synthesizer.synthesize_weekly(ctx)

        cmd = mock_run.call_args[0][0]
        prompt_arg = cmd[-1]
        assert "Focus on fan-in pattern" in prompt_arg

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_thematic_prompt_includes_project_context(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="# Post", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        ctx = _make_thematic_context()
        ctx.project_context = "## Project Context\n\n**Distill**: Content pipeline"
        synthesizer.synthesize_thematic(ctx)

        cmd = mock_run.call_args[0][0]
        prompt_arg = cmd[-1]
        assert "**Distill**: Content pipeline" in prompt_arg

    @patch("distill.blog.synthesizer.subprocess.run")
    def test_adapt_for_platform_with_editorial_hint(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="1/ Adapted thread", stderr=""
        )
        config = BlogConfig()
        synthesizer = BlogSynthesizer(config)
        synthesizer.adapt_for_platform(
            "Blog prose", "twitter", "weekly-W06",
            editorial_hint="Emphasize the fan-in pattern"
        )

        cmd = mock_run.call_args[0][0]
        prompt_arg = cmd[-1]
        assert "EDITORIAL DIRECTION: Emphasize the fan-in pattern" in prompt_arg
