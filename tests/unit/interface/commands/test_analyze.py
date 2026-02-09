"""Tests for the sessions command (analyze sessions skeleton)."""

import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from distill.cli import app
from distill.parsers.claude import ClaudeParser
from distill.parsers.codex import CodexParser

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner(env={"NO_COLOR": "1", "FORCE_COLOR": None})


@pytest.fixture
def temp_dir_with_sessions(tmp_path: Path) -> Path:
    """Create a temporary directory with mock session files."""
    # Create .claude directory structure
    claude_dir = tmp_path / ".claude" / "projects" / "test-project"
    claude_dir.mkdir(parents=True)

    # Create a mock Claude session file
    session_data = [
        {
            "type": "user",
            "timestamp": "2024-01-15T10:00:00Z",
            "message": {"content": "Hello, Claude!"},
        },
        {
            "type": "assistant",
            "timestamp": "2024-01-15T10:00:05Z",
            "message": {"content": "Hello! How can I help?"},
        },
    ]
    session_file = claude_dir / "test-session-001.jsonl"
    with open(session_file, "w") as f:
        for entry in session_data:
            f.write(json.dumps(entry) + "\n")

    # Create .codex directory structure
    codex_dir = tmp_path / ".codex" / "sessions" / "2024" / "01" / "15"
    codex_dir.mkdir(parents=True)

    # Create a mock Codex session file
    codex_session_data = [
        {
            "type": "user",
            "timestamp": "2024-01-15T14:00:00Z",
            "message": {"content": "Help me with code"},
        },
        {
            "type": "assistant",
            "timestamp": "2024-01-15T14:00:10Z",
            "message": {"content": "Sure, I can help!"},
        },
        {
            "type": "user",
            "timestamp": "2024-01-15T14:00:20Z",
            "message": {"content": "Thanks!"},
        },
    ]
    codex_file = codex_dir / "rollout-test-002.jsonl"
    with open(codex_file, "w") as f:
        for entry in codex_session_data:
            f.write(json.dumps(entry) + "\n")

    return tmp_path


class TestSessionsCommand:
    """Tests for the sessions CLI command."""

    def test_sessions_help(self, runner: CliRunner) -> None:
        """Test that sessions --help works and shows expected options."""
        result = runner.invoke(app, ["sessions", "--help"])
        assert result.exit_code == 0
        assert "--dir" in _strip_ansi(result.output)
        assert "json" in _strip_ansi(result.output).lower() or "summary" in _strip_ansi(result.output).lower()

    def test_sessions_empty_directory(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test sessions command with a directory containing no session files."""
        result = runner.invoke(app, ["sessions", "--dir", str(tmp_path)])
        assert result.exit_code == 0

        # Parse the JSON output
        output_data = json.loads(_strip_ansi(result.output))
        assert output_data["session_count"] == 0
        assert output_data["total_messages"] == 0
        assert output_data["date_range"]["start"] is None
        assert output_data["date_range"]["end"] is None

    def test_sessions_with_mock_data(
        self, runner: CliRunner, temp_dir_with_sessions: Path
    ) -> None:
        """Test sessions command with mock Claude and Codex session data."""
        result = runner.invoke(app, ["sessions", "--dir", str(temp_dir_with_sessions)])
        assert result.exit_code == 0

        # Parse the JSON output
        output_data = json.loads(_strip_ansi(result.output))

        # Verify session counts
        assert output_data["session_count"] == 2
        assert output_data["sources"]["claude"] == 1
        assert output_data["sources"]["codex"] == 1

        # Verify total messages (2 from Claude, 3 from Codex)
        assert output_data["total_messages"] == 5

        # Verify date range is present
        assert output_data["date_range"]["start"] is not None
        assert output_data["date_range"]["end"] is not None

    def test_sessions_output_is_valid_json(
        self, runner: CliRunner, temp_dir_with_sessions: Path
    ) -> None:
        """Test that sessions command outputs valid JSON."""
        result = runner.invoke(app, ["sessions", "--dir", str(temp_dir_with_sessions)])
        assert result.exit_code == 0

        # This will raise an exception if the output is not valid JSON
        output_data = json.loads(_strip_ansi(result.output))

        # Verify expected keys exist
        assert "session_count" in output_data
        assert "total_messages" in output_data
        assert "date_range" in output_data
        assert "sources" in output_data


class TestParsersIntegration:
    """Test that CLI correctly uses the existing parsers."""

    def test_claude_parser_is_used(self, temp_dir_with_sessions: Path) -> None:
        """Verify ClaudeParser can parse the mock data."""
        parser = ClaudeParser()
        claude_dir = temp_dir_with_sessions / ".claude"
        sessions = parser.parse_directory(claude_dir)

        assert len(sessions) == 1
        assert len(sessions[0].messages) == 2

    def test_codex_parser_is_used(self, temp_dir_with_sessions: Path) -> None:
        """Verify CodexParser can parse the mock data."""
        parser = CodexParser()
        codex_dir = temp_dir_with_sessions / ".codex"
        sessions = parser.parse_directory(codex_dir)

        assert len(sessions) == 1
        assert len(sessions[0].messages) == 3
