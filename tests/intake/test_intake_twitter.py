"""Tests for the Twitter/X intake publisher."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher
from distill.intake.publishers.twitter import (
    TWITTER_SYSTEM_PROMPT,
    TwitterIntakePublisher,
)


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


class TestTwitterIntakePublisher:
    def test_requires_llm_is_true(self):
        assert TwitterIntakePublisher.requires_llm is True

    def test_is_intake_publisher(self):
        assert issubclass(TwitterIntakePublisher, IntakePublisher)

    def test_daily_output_path(self):
        pub = TwitterIntakePublisher()
        path = pub.daily_output_path(Path("/out"), date(2026, 2, 7))
        assert path == Path("/out/intake/social/twitter/twitter-2026-02-07.md")

    def test_daily_output_path_different_date(self):
        pub = TwitterIntakePublisher()
        path = pub.daily_output_path(Path("/output"), date(2025, 12, 31))
        assert path == Path("/output/intake/social/twitter/twitter-2025-12-31.md")

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_calls_claude_cli(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1/ Hook tweet\n\n2/ Second tweet\n\n3/ Final tweet with CTA",
            stderr="",
        )
        pub = TwitterIntakePublisher()
        result = pub.format_daily(_ctx(), "Some digest prose.")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["claude", "-p"]
        assert call_args[1]["text"] is True
        assert call_args[1]["capture_output"] is True
        assert TWITTER_SYSTEM_PROMPT in call_args[1]["input"]
        assert "Some digest prose." in call_args[1]["input"]
        assert result == "1/ Hook tweet\n\n2/ Second tweet\n\n3/ Final tweet with CTA"

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_strips_output(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  1/ Thread content  \n\n",
            stderr="",
        )
        pub = TwitterIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == "1/ Thread content"

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_returns_empty_on_nonzero_exit(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )
        pub = TwitterIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_returns_empty_on_file_not_found(self, mock_run: MagicMock):
        mock_run.side_effect = FileNotFoundError("claude not found")
        pub = TwitterIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_returns_empty_on_timeout(self, mock_run: MagicMock):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        pub = TwitterIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_returns_empty_on_os_error(self, mock_run: MagicMock):
        mock_run.side_effect = OSError("permission denied")
        pub = TwitterIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")
        assert result == ""

    @patch("distill.intake.publishers.twitter.subprocess.run")
    def test_format_daily_prompt_contains_system_and_prose(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1/ Thread",
            stderr="",
        )
        pub = TwitterIntakePublisher()
        pub.format_daily(_ctx(), "My digest content here.")

        sent_input = mock_run.call_args[1]["input"]
        assert "Convert this daily research digest" in sent_input
        assert "280 characters" in sent_input
        assert "My digest content here." in sent_input
