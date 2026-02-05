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

    def test_analyze_default_output(self, runner: CliRunner) -> None:
        """Test that analyze uses default output directory when --output is not specified."""
        result = runner.invoke(app, ["analyze", "--dir", "/tmp"])
        # Should succeed (exit 0) even without --output, using default ./insights/
        assert result.exit_code == 0
        assert "Output will be written to:" in result.output
