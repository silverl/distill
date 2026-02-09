"""End-to-end CLI subprocess tests for session-insights.

These tests invoke the CLI as a real subprocess and validate output,
exit codes, and generated filesystem artifacts.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# Derive PYTHONPATH from this file's location (tests/integration/ -> src/)
SRC_DIR = str(Path(__file__).parents[2] / "src")


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the session-insights CLI as a subprocess.

    Args:
        *args: CLI arguments (e.g., "analyze", "--dir", "/tmp/x").
        cwd: Working directory for the subprocess.

    Returns:
        CompletedProcess with captured stdout/stderr.
    """
    env = {**os.environ, "PYTHONPATH": SRC_DIR, "NO_COLOR": "1"}
    env.pop("FORCE_COLOR", None)
    return subprocess.run(
        [sys.executable, "-m", "distill", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


@pytest.fixture
def sample_claude_history(tmp_path: Path) -> Path:
    """Create a sample .claude directory with project session data."""
    project_dir = tmp_path / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)

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
            "timestamp": (now - timedelta(hours=2) + timedelta(minutes=1)).isoformat(),
        },
        {
            "type": "user",
            "message": {"content": "Add unit tests for the login module"},
            "timestamp": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "I'll add those tests."},
            "timestamp": (now - timedelta(hours=1) + timedelta(minutes=1)).isoformat(),
        },
    ]

    session_file = project_dir / "session.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for entry in session_entries:
            f.write(json.dumps(entry) + "\n")

    return tmp_path


class TestCLIEndToEnd:
    """End-to-end subprocess tests for the session-insights CLI."""

    def test_help_output(self, tmp_path: Path) -> None:
        """Verify --help returns expected commands."""
        result = _run_cli("--help", cwd=tmp_path)

        assert result.returncode == 0
        # Should list the main commands
        assert "analyze" in result.stdout
        assert "sessions" in result.stdout

    def test_sessions_command_with_sample_data(
        self, sample_claude_history: Path
    ) -> None:
        """Run sessions --dir with fixture data, validate JSON output."""
        result = _run_cli(
            "sessions", "--dir", str(sample_claude_history),
            cwd=sample_claude_history,
        )

        assert result.returncode == 0

        # Parse and validate JSON schema
        data = json.loads(result.stdout)
        assert "session_count" in data
        assert "total_messages" in data
        assert "date_range" in data
        assert "sources" in data
        assert isinstance(data["session_count"], int)
        assert data["session_count"] > 0
        assert isinstance(data["sources"], dict)
        assert "claude" in data["sources"]
        assert data["sources"]["claude"] > 0

    def test_analyze_command_with_sample_data(
        self, sample_claude_history: Path, tmp_path: Path
    ) -> None:
        """Run analyze with fixture data, verify Obsidian notes generated."""
        output_dir = tmp_path / "output"

        result = _run_cli(
            "analyze",
            "--dir", str(sample_claude_history),
            "--output", str(output_dir),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Analysis complete" in result.stdout

        # Verify filesystem artifacts
        sessions_dir = output_dir / "sessions"
        daily_dir = output_dir / "daily"
        index_path = output_dir / "index.md"

        # Sessions directory should have at least 1 .md file
        session_files = list(sessions_dir.glob("*.md"))
        assert len(session_files) >= 1, "No session .md files generated"

        # Daily directory should have at least 1 .md file
        daily_files = list(daily_dir.glob("*.md"))
        assert len(daily_files) >= 1, "No daily summary .md files generated"

        # Index file should exist with expected frontmatter
        assert index_path.exists(), "index.md not generated"
        index_content = index_path.read_text(encoding="utf-8")
        assert "type: index" in index_content
        assert "total_sessions:" in index_content
        assert "Session Insights Index" in index_content

    def test_analyze_with_date_filter(
        self, sample_claude_history: Path, tmp_path: Path
    ) -> None:
        """Run analyze with --since flag, verify date filtering works."""
        output_dir = tmp_path / "output"

        # Use a future date — should find no sessions after filtering
        future_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        result = _run_cli(
            "analyze",
            "--dir", str(sample_claude_history),
            "--output", str(output_dir),
            "--since", future_date,
            cwd=tmp_path,
        )

        # Should exit cleanly with "no sessions" message
        assert result.returncode == 0
        assert "No sessions found" in result.stdout

    def test_sessions_no_data(self, tmp_path: Path) -> None:
        """Run sessions against empty directory, verify graceful exit."""
        result = _run_cli(
            "sessions", "--dir", str(tmp_path),
            cwd=tmp_path,
        )

        assert result.returncode == 0

        # Should return valid JSON with zero counts
        data = json.loads(result.stdout)
        assert data["session_count"] == 0
        assert data["total_messages"] == 0

    def test_analyze_invalid_format(self, tmp_path: Path) -> None:
        """Run analyze with invalid --format, verify error exit."""
        result = _run_cli(
            "analyze",
            "--dir", str(tmp_path),
            "--format", "invalid_format",
            cwd=tmp_path,
        )

        assert result.returncode == 1
        assert "Unsupported format" in result.stdout or "Error" in result.stdout

    def test_analyze_stats_only_with_data(
        self, sample_claude_history: Path, tmp_path: Path
    ) -> None:
        """Run analyze --stats-only and verify JSON output."""
        result = _run_cli(
            "analyze",
            "--dir", str(sample_claude_history),
            "--stats-only",
            cwd=tmp_path,
        )

        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert "session_count" in data
        assert "content_richness_score" in data
        assert "field_coverage" in data
        assert data["session_count"] > 0
        assert isinstance(data["content_richness_score"], float)
        assert isinstance(data["field_coverage"], dict)

    def test_analyze_stats_only_empty_dir(self, tmp_path: Path) -> None:
        """Run analyze --stats-only on empty dir, verify zero-count JSON."""
        result = _run_cli(
            "analyze",
            "--dir", str(tmp_path),
            "--stats-only",
            cwd=tmp_path,
        )

        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert data["session_count"] == 0
        assert data["content_richness_score"] == 0.0

    def test_analyze_stats_only_no_files_created(
        self, sample_claude_history: Path, tmp_path: Path
    ) -> None:
        """--stats-only should not create any output files."""
        output_dir = tmp_path / "no_output"
        result = _run_cli(
            "analyze",
            "--dir", str(sample_claude_history),
            "--output", str(output_dir),
            "--stats-only",
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert not output_dir.exists()
