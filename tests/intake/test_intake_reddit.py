"""Tests for the Reddit intake publisher."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher
from distill.intake.publishers.reddit import REDDIT_SYSTEM_PROMPT, RedditIntakePublisher


def _ctx() -> DailyIntakeContext:
    return DailyIntakeContext(
        date=date(2026, 2, 7),
        total_items=5,
        total_word_count=1500,
        sources=["rss"],
        sites=["Blog A", "Blog B"],
        all_tags=["python", "ai"],
        combined_text="Combined text here.",
    )


class TestRedditIntakePublisher:
    def test_requires_llm_attribute(self):
        assert RedditIntakePublisher.requires_llm is True

    def test_is_intake_publisher(self):
        assert issubclass(RedditIntakePublisher, IntakePublisher)

    def test_daily_output_path(self):
        pub = RedditIntakePublisher()
        path = pub.daily_output_path(Path("/output"), date(2026, 2, 7))
        assert path == Path("/output/intake/social/reddit/reddit-2026-02-07.md")

    def test_daily_output_path_different_date(self):
        pub = RedditIntakePublisher()
        path = pub.daily_output_path(Path("/out"), date(2025, 12, 31))
        assert path == Path("/out/intake/social/reddit/reddit-2025-12-31.md")

    @patch("distill.intake.publishers.reddit.subprocess.run")
    def test_format_daily_calls_subprocess(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="**TL;DR** Great stuff\n\nReddit post body.",
            stderr="",
        )
        pub = RedditIntakePublisher()
        result = pub.format_daily(_ctx(), "Daily digest prose.")

        mock_run.assert_called_once_with(
            ["claude", "-p"],
            input=f"{REDDIT_SYSTEM_PROMPT}\n\n---\n\nDaily digest prose.",
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result == "**TL;DR** Great stuff\n\nReddit post body."

    @patch("distill.intake.publishers.reddit.subprocess.run")
    def test_format_daily_returns_stripped_output(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  Reddit post with whitespace  \n\n",
            stderr="",
        )
        pub = RedditIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == "Reddit post with whitespace"

    @patch("distill.intake.publishers.reddit.subprocess.run")
    def test_format_daily_nonzero_exit_returns_empty(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )
        pub = RedditIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.reddit.subprocess.run")
    def test_format_daily_file_not_found_returns_empty(self, mock_run: MagicMock):
        mock_run.side_effect = FileNotFoundError("claude not found")
        pub = RedditIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.reddit.subprocess.run")
    def test_format_daily_timeout_returns_empty(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        pub = RedditIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.reddit.subprocess.run")
    def test_format_daily_os_error_returns_empty(self, mock_run: MagicMock):
        mock_run.side_effect = OSError("permission denied")
        pub = RedditIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    def test_system_prompt_contains_structure(self):
        assert "TL;DR" in REDDIT_SYSTEM_PROMPT
        assert "What I Read Today" in REDDIT_SYSTEM_PROMPT
        assert "Discussion question" in REDDIT_SYSTEM_PROMPT
        assert "r/programming" in REDDIT_SYSTEM_PROMPT
