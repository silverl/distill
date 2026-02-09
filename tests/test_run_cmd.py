"""Tests for the 'distill run' CLI command."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from distill.cli import app

runner = CliRunner()


@pytest.fixture()
def output_dir(tmp_path):
    """Create output directory with journal subdirectory."""
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    # Write a minimal journal entry so blog generation can find it
    content = """---
date: 2026-02-07
sessions_count: 3
duration_minutes: 120
tags:
  - python
projects:
  - distill
---

# Journal Entry

Built session parser today.
"""
    (journal_dir / "2026-02-07.md").write_text(content)
    return tmp_path


class TestRunCommand:
    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_full_pipeline(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = [output_dir / "journal" / "entry.md"]
        mock_intake.return_value = [output_dir / "intake" / "digest.md"]
        mock_blog.return_value = [output_dir / "blog" / "post.md"]

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir)],
        )
        assert result.exit_code == 0
        assert "Pipeline complete" in result.output
        mock_discover.assert_called_once()
        mock_journal.assert_called_once()
        mock_intake.assert_called_once()
        mock_blog.assert_called_once()

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_skip_sessions(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_intake.return_value = []
        mock_blog.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir), "--skip-sessions"],
        )
        assert result.exit_code == 0
        assert "skipped" in result.output
        mock_discover.assert_not_called()
        mock_journal.assert_not_called()

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_skip_intake(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = []
        mock_blog.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir), "--skip-intake"],
        )
        assert result.exit_code == 0
        mock_intake.assert_not_called()

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_skip_blog(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = []
        mock_intake.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir), "--skip-blog"],
        )
        assert result.exit_code == 0
        mock_blog.assert_not_called()

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_dry_run(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = []
        mock_intake.return_value = []
        mock_blog.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir), "--dry-run"],
        )
        assert result.exit_code == 0
        # dry_run should be passed through to sub-functions
        _, kwargs = mock_journal.call_args
        assert kwargs["dry_run"] is True

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_error_in_one_step_continues(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.side_effect = RuntimeError("discover failed")
        mock_intake.return_value = [output_dir / "intake" / "digest.md"]
        mock_blog.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir)],
        )
        assert result.exit_code == 0
        # Should still run intake and blog despite session error
        mock_intake.assert_called_once()
        assert "error" in result.output.lower()

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_force_flag(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = []
        mock_intake.return_value = []
        mock_blog.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(output_dir), "--dir", str(output_dir), "--force"],
        )
        assert result.exit_code == 0
        _, kwargs = mock_journal.call_args
        assert kwargs["force"] is True

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    @patch("distill.cli.generate_blog_posts")
    def test_publish_platforms(
        self,
        mock_blog,
        mock_intake,
        mock_journal,
        mock_discover,
        output_dir,
    ):
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = []
        mock_intake.return_value = []
        mock_blog.return_value = []

        result = runner.invoke(
            app,
            [
                "run",
                "--output", str(output_dir),
                "--dir", str(output_dir),
                "--publish", "obsidian,markdown",
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_blog.call_args
        assert kwargs["platforms"] == ["obsidian", "markdown"]

    @patch("distill.cli._discover_and_parse")
    @patch("distill.cli.generate_journal_notes")
    @patch("distill.cli.generate_intake")
    def test_skip_blog_when_no_journal(
        self,
        mock_intake,
        mock_journal,
        mock_discover,
        tmp_path,
    ):
        """Blog step should be skipped gracefully if no journal/ dir exists."""
        mock_discover.return_value = [MagicMock()]
        mock_journal.return_value = []
        mock_intake.return_value = []

        result = runner.invoke(
            app,
            ["run", "--output", str(tmp_path), "--dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "No journal entries yet" in result.output
