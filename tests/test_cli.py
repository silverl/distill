"""Smoke tests for the CLI."""

import pytest
from typer.testing import CliRunner

from session_insights.cli import app


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestCLI:
    """Tests for the CLI entry point."""

    def test_main_help(self, runner: CliRunner) -> None:
        """Test that --help works on the main command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "session-insights" in result.output.lower() or "analyze" in result.output.lower()

    def test_main_version(self, runner: CliRunner) -> None:
        """Test that --version works."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "session-insights" in result.output

    def test_analyze_help(self, runner: CliRunner) -> None:
        """Test that analyze --help works."""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "output" in result.output.lower()

    def test_analyze_missing_path(self, runner: CliRunner) -> None:
        """Test that analyze requires a session path."""
        result = runner.invoke(app, ["analyze"])
        assert result.exit_code != 0
