"""Integration tests for the session-insights CLI and pipeline."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

from distill.core import (
    AnalysisResult,
    analyze,
    discover_sessions,
    parse_session_file,
)
from distill.formatters.obsidian import ObsidianFormatter
from distill.models import ToolUsage
from distill.parsers.models import BaseSession  # Use parser's BaseSession


@pytest.fixture
def sample_claude_history(tmp_path: Path) -> Path:
    """Create a sample .claude directory with project sessions."""
    # Create .claude/projects/test-project/ structure (what ClaudeParser expects)
    project_dir = tmp_path / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    # Create sample session entries (ClaudeParser expects conversation format)
    now = datetime.now()
    session_entries = [
        {
            "type": "user",
            "message": {"content": "Help me fix the authentication bug"},
            "timestamp": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "I'll help you fix that bug."},
            "timestamp": (now - timedelta(hours=2, minutes=-1)).isoformat(),
        },
        {
            "type": "user",
            "message": {"content": "Add unit tests for the login module"},
            "timestamp": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "I'll add those tests."},
            "timestamp": (now - timedelta(hours=1, minutes=-1)).isoformat(),
        },
        {
            "type": "user",
            "message": {"content": "Refactor the database connection pool"},
            "timestamp": now.isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "I'll refactor that for you."},
            "timestamp": (now + timedelta(minutes=1)).isoformat(),
        },
    ]

    session_file = project_dir / "session.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for entry in session_entries:
            f.write(json.dumps(entry) + "\n")

    return tmp_path


@pytest.fixture
def sample_vermas_session(tmp_path: Path) -> Path:
    """Create a sample .vermas directory with workflow state data."""
    # Create .vermas/state/mission-xxx-cycle-1-execute-task/ structure
    state_dir = tmp_path / ".vermas" / "state" / "mission-abc123-cycle-1-execute-implement-feature"
    signals_dir = state_dir / "signals"
    signals_dir.mkdir(parents=True)

    now = datetime.now()

    # Create a signal file (YAML format as VermasParser expects)
    # Uses 'created_at' field (not 'timestamp') as expected by parser
    signal_data = f"""signal: done
agent_id: dev-001
role: dev
created_at: "{now.isoformat()}"
message: "Completed implementation of feature X"
workflow_id: "wf-abc123"
"""
    signal_file = signals_dir / "signal-001.yaml"
    signal_file.write_text(signal_data, encoding="utf-8")

    return tmp_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create an output directory for notes."""
    output = tmp_path / "obsidian_notes"
    output.mkdir()
    return output


class TestDiscoverSessions:
    """Tests for session discovery."""

    def test_discover_claude_sessions(self, sample_claude_history: Path) -> None:
        """Test discovering Claude source root directory."""
        discovered = discover_sessions(sample_claude_history, sources=["claude"])

        assert "claude" in discovered
        assert len(discovered["claude"]) == 1
        # Now returns the .claude directory, not individual files
        assert discovered["claude"][0].name == ".claude"

    def test_discover_vermas_sessions(self, sample_vermas_session: Path) -> None:
        """Test discovering VerMAS source root directory."""
        discovered = discover_sessions(sample_vermas_session, sources=["vermas"])

        assert "vermas" in discovered
        assert len(discovered["vermas"]) == 1
        # Now returns the .vermas directory, not individual files
        assert discovered["vermas"][0].name == ".vermas"

    def test_discover_all_sources(
        self, sample_claude_history: Path, sample_vermas_session: Path
    ) -> None:
        """Test discovering from all sources."""
        # Combine the sample directories
        discovered = discover_sessions(sample_claude_history, sources=None)

        # Should find at least claude
        assert len(discovered) >= 1

    def test_discover_nonexistent_source(self, tmp_path: Path) -> None:
        """Test discovering with nonexistent source."""
        discovered = discover_sessions(tmp_path, sources=["nonexistent"])

        assert discovered == {}

    def test_discover_empty_directory(self, tmp_path: Path) -> None:
        """Test discovering in empty directory."""
        discovered = discover_sessions(tmp_path)

        assert discovered == {}

    def test_discover_with_include_home(self, tmp_path: Path) -> None:
        """Test that include_home adds home directory sources."""
        # Create a .claude dir in tmp_path
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "projects").mkdir()

        # include_home=True should not crash and should return at least the local dir
        discovered = discover_sessions(tmp_path, include_home=True)
        assert "claude" in discovered
        # The local .claude dir should be included
        assert any(p.parent == tmp_path for p in discovered["claude"])

    def test_discover_include_home_no_duplicate(self, tmp_path: Path) -> None:
        """Test that include_home doesn't duplicate when dir==home."""
        # When scanning home dir itself, include_home shouldn't duplicate
        discovered = discover_sessions(tmp_path, include_home=False)
        discovered_with_home = discover_sessions(tmp_path, include_home=True)
        # Should not have duplicate paths for the same source
        for source, paths in discovered_with_home.items():
            assert len(paths) == len(set(paths)), f"Duplicate paths for {source}"


class TestParseSessionFile:
    """Tests for parsing session files."""

    def test_parse_claude_history(self, sample_claude_history: Path) -> None:
        """Test parsing Claude sessions from .claude directory."""
        claude_dir = sample_claude_history / ".claude"
        sessions = parse_session_file(claude_dir, "claude")

        # Should find sessions from the project directory
        assert len(sessions) >= 1
        assert all(isinstance(s, BaseSession) for s in sessions)
        # ClaudeSession uses "claude-code" as source, not "claude"
        assert all(s.source == "claude-code" for s in sessions)

    def test_parse_vermas_session(self, sample_vermas_session: Path) -> None:
        """Test parsing VerMAS sessions from .vermas directory."""
        vermas_dir = sample_vermas_session / ".vermas"
        sessions = parse_session_file(vermas_dir, "vermas")

        # Should find the mission workflow session
        assert len(sessions) >= 1
        assert all(s.source == "vermas" for s in sessions)

    def test_parse_invalid_source(self, tmp_path: Path) -> None:
        """Test parsing with unknown source type."""
        sessions = parse_session_file(tmp_path, "unknown")
        assert sessions == []

    def test_parse_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test parsing nonexistent directory."""
        sessions = parse_session_file(tmp_path / "nonexistent", "claude")
        assert sessions == []


class TestAnalyze:
    """Tests for session analysis."""

    def test_analyze_empty_sessions(self) -> None:
        """Test analyzing empty session list."""
        result = analyze([])

        assert isinstance(result, AnalysisResult)
        assert result.sessions == []
        assert result.stats.total_sessions == 0

    def test_analyze_single_session(self) -> None:
        """Test analyzing a single session."""
        session = BaseSession(
            session_id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 0),
            source="claude",
            summary="Test session",
        )
        result = analyze([session])

        assert len(result.sessions) == 1
        assert result.stats.total_sessions == 1
        assert result.stats.sources["claude"] == 1

    def test_analyze_multiple_sessions(self) -> None:
        """Test analyzing multiple sessions."""
        from distill.parsers.models import ToolUsage as ParserToolUsage

        sessions = [
            BaseSession(
                session_id=f"test-{i:03d}",
                timestamp=datetime(2024, 1, 15, 10 + i, 0),
                source="claude" if i % 2 == 0 else "vermas",
                summary=f"Session {i}",
                tool_calls=[ParserToolUsage(tool_name="Read")] * (i + 1),
            )
            for i in range(5)
        ]
        result = analyze(sessions)

        assert result.stats.total_sessions == 5
        assert len(result.stats.sources) == 2
        assert len(result.patterns) > 0

    def test_analyze_detects_patterns(self) -> None:
        """Test that analysis detects patterns."""
        from distill.parsers.models import ToolUsage as ParserToolUsage

        sessions = [
            BaseSession(
                session_id=f"test-{i:03d}",
                timestamp=datetime(2024, 1, 15, 14, 0),  # All at 2 PM
                source="claude",
                tool_calls=[ParserToolUsage(tool_name="Read")] * 5,
            )
            for i in range(10)
        ]
        result = analyze(sessions)

        # Should detect peak hour pattern
        peak_hour_pattern = next(
            (p for p in result.patterns if p.name == "peak_activity_hour"), None
        )
        assert peak_hour_pattern is not None
        assert peak_hour_pattern.metadata["hour"] == 14


class TestEndToEndPipeline:
    """End-to-end integration tests."""

    def test_full_pipeline(
        self, sample_claude_history: Path, output_dir: Path
    ) -> None:
        """Test the complete analysis pipeline."""
        # 1. Discover sessions
        discovered = discover_sessions(sample_claude_history, sources=["claude"])
        assert discovered

        # 2. Parse sessions
        all_sessions: list[BaseSession] = []
        for source, files in discovered.items():
            for file_path in files:
                sessions = parse_session_file(file_path, source)
                all_sessions.extend(sessions)

        assert len(all_sessions) > 0

        # 3. Analyze
        result = analyze(all_sessions)
        assert result.stats.total_sessions > 0

        # 4. Format and write
        formatter = ObsidianFormatter(include_conversation=False)
        sessions_dir = output_dir / "sessions"
        sessions_dir.mkdir()

        for session in result.sessions:
            note = formatter.format_session(session)
            note_path = sessions_dir / f"{session.note_name}.md"
            note_path.write_text(note, encoding="utf-8")

        # Verify output
        md_files = list(sessions_dir.glob("*.md"))
        assert len(md_files) == len(result.sessions)

    def test_pipeline_with_date_filter(
        self, sample_claude_history: Path
    ) -> None:
        """Test pipeline with date filtering."""
        discovered = discover_sessions(sample_claude_history, sources=["claude"])

        all_sessions: list[BaseSession] = []
        for source, files in discovered.items():
            for file_path in files:
                sessions = parse_session_file(file_path, source)
                all_sessions.extend(sessions)

        # Filter to future date (should get nothing)
        future_date = (datetime.now() + timedelta(days=1)).date()
        filtered = [s for s in all_sessions if s.start_time.date() >= future_date]

        assert len(filtered) == 0


class TestCLIExitCodes:
    """Tests for CLI exit codes and error handling."""

    @pytest.fixture
    def cli_path(self) -> Path:
        """Get path to CLI module."""
        return Path(__file__).parents[2] / "src" / "distill" / "cli.py"

    def test_cli_version(self, cli_path: Path) -> None:
        """Test CLI version flag."""
        result = subprocess.run(
            [sys.executable, "-m", "distill.cli", "--version"],
            capture_output=True,
            text=True,
            cwd=cli_path.parents[2],
            env={**os.environ, "PYTHONPATH": str(cli_path.parents[2] / "src")},
        )
        # Allow either 0 or 1 (typer raises Exit on version)
        assert result.returncode in (0, 1)
        # Should contain version info
        assert "session-insights" in _strip_ansi(result.stdout) or "0.1.0" in _strip_ansi(result.stdout)

    def test_cli_default_output(self, cli_path: Path, tmp_path: Path) -> None:
        """Test CLI exits cleanly when no sessions found in empty directory."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "distill.cli",
                "analyze",
                "--dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=cli_path.parents[2],
            env={**os.environ, "PYTHONPATH": str(cli_path.parents[2] / "src")},
        )
        # Should succeed (exit 0) even with no sessions
        assert result.returncode == 0

    def test_cli_invalid_date(
        self, cli_path: Path, tmp_path: Path, output_dir: Path
    ) -> None:
        """Test CLI with invalid date format."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "distill.cli",
                "analyze",
                "--dir",
                str(tmp_path),
                "--output",
                str(output_dir),
                "--since",
                "not-a-date",
            ],
            capture_output=True,
            text=True,
            cwd=cli_path.parents[2],
            env={**os.environ, "PYTHONPATH": str(cli_path.parents[2] / "src")},
        )
        assert result.returncode == 1
        assert "Invalid date" in _strip_ansi(result.stdout) or "Invalid date" in _strip_ansi(result.stderr) or "Error" in _strip_ansi(result.stdout)
