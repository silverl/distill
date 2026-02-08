"""Tests for LinkedIn intake publisher."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.linkedin import (
    LINKEDIN_SYSTEM_PROMPT,
    LinkedInIntakePublisher,
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


class TestLinkedInIntakePublisher:
    def test_requires_llm_attribute(self):
        pub = LinkedInIntakePublisher()
        assert pub.requires_llm is True

    def test_daily_output_path(self):
        pub = LinkedInIntakePublisher()
        path = pub.daily_output_path(Path("/out"), date(2026, 2, 7))
        assert path == Path("/out/intake/social/linkedin/linkedin-2026-02-07.md")

    def test_daily_output_path_different_date(self):
        pub = LinkedInIntakePublisher()
        path = pub.daily_output_path(Path("/output"), date(2025, 12, 31))
        assert path == Path("/output/intake/social/linkedin/linkedin-2025-12-31.md")

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_calls_subprocess(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude", "-p"],
            returncode=0,
            stdout="LinkedIn post content here\n",
            stderr="",
        )
        pub = LinkedInIntakePublisher()
        result = pub.format_daily(_ctx(), "Daily digest prose.")

        assert result == "LinkedIn post content here"
        mock_run.assert_called_once()

        call_kwargs = mock_run.call_args
        assert call_kwargs[0][0] == ["claude", "-p"]
        assert call_kwargs[1]["input"].startswith(LINKEDIN_SYSTEM_PROMPT)
        assert "Daily digest prose." in call_kwargs[1]["input"]
        assert call_kwargs[1]["capture_output"] is True
        assert call_kwargs[1]["text"] is True

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_prompt_structure(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude", "-p"],
            returncode=0,
            stdout="Post output",
            stderr="",
        )
        pub = LinkedInIntakePublisher()
        pub.format_daily(_ctx(), "Some digest prose.")

        prompt = mock_run.call_args[1]["input"]
        # Prompt should contain system prompt, separator, then prose
        assert LINKEDIN_SYSTEM_PROMPT in prompt
        assert "\n\n---\n\n" in prompt
        assert "Some digest prose." in prompt

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_nonzero_return_code(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude", "-p"],
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )
        pub = LinkedInIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")

        assert result == ""

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("claude not found")
        pub = LinkedInIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")

        assert result == ""

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        pub = LinkedInIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")

        assert result == ""

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_os_error(self, mock_run):
        mock_run.side_effect = OSError("Permission denied")
        pub = LinkedInIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")

        assert result == ""

    @patch("distill.intake.publishers.linkedin.subprocess.run")
    def test_format_daily_strips_output(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude", "-p"],
            returncode=0,
            stdout="  \n  LinkedIn post  \n  ",
            stderr="",
        )
        pub = LinkedInIntakePublisher()
        result = pub.format_daily(_ctx(), "Prose.")

        assert result == "LinkedIn post"
