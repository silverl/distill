"""Negative-path CLI tests for session-insights robustness.

Tests cover: malformed input files, missing directories, permission errors,
empty session files, edge cases, and --global flag discovery behavior.

Each test verifies the CLI exits cleanly — exit code 0 with warning, or
well-formed error message with non-zero exit code — and never produces
Python tracebacks in output.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from session_insights.cli import app

# Derive PYTHONPATH for subprocess tests
SRC_DIR = str(Path(__file__).parents[1] / "src")


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the CLI as a subprocess (for E2E traceback checks)."""
    return subprocess.run(
        [sys.executable, "-m", "session_insights", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": SRC_DIR},
    )


def _assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    """Assert that neither stdout nor stderr contains a Python traceback."""
    for output in (result.stdout, result.stderr):
        assert "Traceback (most recent call last)" not in output, (
            f"CLI produced a traceback:\n{output}"
        )


# ---------------------------------------------------------------------------
# 1. Malformed input files
# ---------------------------------------------------------------------------
class TestMalformedInputFiles:
    """Tests for malformed/corrupt session files."""

    def test_truncated_json_in_session_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Truncated JSON (missing closing brace) is handled gracefully."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"
        session_file.write_text(
            '{"type": "user", "message": {"content": "hello"}\n'  # missing }
        )

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        # Should not crash — graceful handling
        assert "Traceback" not in result.output

    def test_invalid_jsonl_lines_mixed_with_valid(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """File with some valid and some invalid JSONL lines is processed."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"

        lines = [
            json.dumps({"type": "user", "message": {"content": "hello"}, "timestamp": datetime.now().isoformat()}),
            "THIS IS NOT JSON AT ALL",
            json.dumps({"type": "assistant", "message": {"content": "hi"}, "timestamp": datetime.now().isoformat()}),
            "{malformed json!!! %%",
            "",  # empty line (should be skipped)
        ]
        session_file.write_text("\n".join(lines) + "\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_binary_garbage_in_session_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Binary/garbage content in a .jsonl file is handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"
        session_file.write_bytes(b"\x00\xff\xfe\x80\x90\xab\xcd\xef")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_corrupted_session_state_partial_write(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Session file that looks like a partial/interrupted write."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"
        # Simulate a partial write: valid line + truncated line
        session_file.write_text(
            '{"type": "user", "message": {"content": "hello"}, "timestamp": "2024-01-15T10:00:00Z"}\n'
            '{"type": "assistant", "messa'
        )

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_json_array_instead_of_jsonl(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """A .jsonl file containing a JSON array instead of lines."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"
        session_file.write_text(json.dumps([
            {"type": "user", "message": {"content": "hello"}},
            {"type": "assistant", "message": {"content": "world"}},
        ]))

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_malformed_codex_session(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Malformed Codex session file is handled gracefully."""
        codex_dir = tmp_path / ".codex" / "sessions" / "2024" / "01" / "15"
        codex_dir.mkdir(parents=True)
        session_file = codex_dir / "rollout-abc123.jsonl"
        session_file.write_text("not json at all\n{broken\n")

        result = runner.invoke(app, ["sessions", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output
        # Should still produce valid JSON output
        data = json.loads(result.output)
        assert "session_count" in data

    def test_malformed_input_e2e_no_traceback(self, tmp_path: Path) -> None:
        """E2E: malformed session files produce no Python tracebacks."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "bad.jsonl").write_text("{{{{not valid json}}}}\n" * 10)

        result = _run_cli("analyze", "--dir", str(tmp_path), cwd=tmp_path)
        _assert_no_traceback(result)


# ---------------------------------------------------------------------------
# 2. Missing directories
# ---------------------------------------------------------------------------
class TestMissingDirectories:
    """Tests for --dir pointing to non-existent or empty paths."""

    def test_dir_nonexistent_path(self, runner: CliRunner) -> None:
        """--dir pointing to a non-existent path produces a clean error."""
        result = runner.invoke(app, ["analyze", "--dir", "/tmp/does_not_exist_xyz_123"])
        # Typer validates exists=True and returns exit code 2
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_dir_nonexistent_path_sessions_cmd(self, runner: CliRunner) -> None:
        """sessions --dir with non-existent path produces a clean error."""
        result = runner.invoke(app, ["sessions", "--dir", "/tmp/does_not_exist_xyz_123"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_dir_is_a_file_not_directory(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--dir pointing to a file (not directory) produces a clean error."""
        some_file = tmp_path / "not_a_dir.txt"
        some_file.write_text("just a file")

        result = runner.invoke(app, ["analyze", "--dir", str(some_file)])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_empty_directory_no_source_dirs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Empty directory with no .claude/.codex/.vermas dirs exits cleanly."""
        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No session files found" in result.output

    def test_claude_dir_exists_but_no_projects(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Directory with .claude/ but no projects/ subdir exits cleanly."""
        (tmp_path / ".claude").mkdir()
        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_nonexistent_dir_e2e_no_traceback(self, tmp_path: Path) -> None:
        """E2E: non-existent --dir produces no traceback."""
        result = _run_cli(
            "analyze", "--dir", "/tmp/absolutely_not_a_real_path_abc",
            cwd=tmp_path,
        )
        _assert_no_traceback(result)
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# 3. Permission errors (mocked)
# ---------------------------------------------------------------------------
class TestPermissionErrors:
    """Tests for unreadable session files using mocking."""

    def test_unreadable_session_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Unreadable session file (PermissionError) is handled gracefully."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"
        session_file.write_text('{"type": "user", "message": {"content": "x"}}\n')

        # Mock open() to raise PermissionError for the session file
        original_open = open

        def mock_open(path, *args, **kwargs):
            if str(path) == str(session_file):
                raise PermissionError(f"Permission denied: '{path}'")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_unreadable_directory_iterdir(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Unreadable project directory (iterdir raises) is handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "session.jsonl").write_text("{}\n")

        original_iterdir = Path.iterdir

        def mock_iterdir(self_path):
            if self_path == project_dir:
                raise PermissionError(f"Permission denied: '{self_path}'")
            return original_iterdir(self_path)

        with patch.object(Path, "iterdir", mock_iterdir):
            result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])

        # May exit 0 (no sessions found) or handle the error
        assert "Traceback" not in result.output

    def test_sessions_cmd_permission_error_on_parse(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """sessions command handles PermissionError during parsing."""
        claude_dir = tmp_path / ".claude" / "projects" / "test"
        claude_dir.mkdir(parents=True)
        (claude_dir / "session.jsonl").write_text('{"type": "user"}\n')

        original_open = open

        def mock_open(path, *args, **kwargs):
            path_str = str(path)
            if path_str.endswith(".jsonl"):
                raise PermissionError(f"Permission denied: '{path}'")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            result = runner.invoke(app, ["sessions", "--dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# 4. Empty session files
# ---------------------------------------------------------------------------
class TestEmptySessionFiles:
    """Tests for empty or trivial session files."""

    def test_zero_byte_session_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Zero-byte .jsonl file is handled gracefully."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "empty.jsonl").write_text("")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_file_with_only_whitespace(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Session file with only whitespace/newlines is handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "whitespace.jsonl").write_text("\n\n\n   \n\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_valid_json_but_empty_array(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Valid JSON file with empty array '[]' is handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "empty_array.json").write_text("[]")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_valid_json_but_empty_object(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Valid JSON file with empty object '{}' is handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "empty_obj.jsonl").write_text("{}\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_sessions_cmd_zero_byte_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """sessions command handles zero-byte session files."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        (project_dir / "empty.jsonl").write_text("")

        result = runner.invoke(app, ["sessions", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_count"] == 0

    def test_codex_zero_byte_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Codex zero-byte session file is handled."""
        codex_dir = tmp_path / ".codex" / "sessions"
        codex_dir.mkdir(parents=True)
        (codex_dir / "rollout-empty.jsonl").write_text("")

        result = runner.invoke(app, ["sessions", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data["session_count"], int)


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    """Tests for edge cases: large files, missing messages, system-only, etc."""

    def test_session_with_no_messages(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Session file with entries but no user/assistant messages."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        # Only metadata entries, no type=user or type=assistant
        lines = [
            json.dumps({"sessionId": "abc", "timestamp": "2024-01-15T10:00:00Z"}),
            json.dumps({"version": "1.0.0", "cwd": "/tmp"}),
        ]
        (project_dir / "no_msg.jsonl").write_text("\n".join(lines) + "\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_session_with_only_system_messages(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Session with only system-type entries (no user/assistant)."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        lines = [
            json.dumps({"type": "system", "message": {"content": "init"}, "timestamp": "2024-01-15T10:00:00Z"}),
            json.dumps({"type": "system", "message": {"content": "config"}, "timestamp": "2024-01-15T10:00:01Z"}),
        ]
        (project_dir / "system_only.jsonl").write_text("\n".join(lines) + "\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_very_large_session_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Large session file with many entries is handled without crash."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        session_file = project_dir / "large.jsonl"

        now = datetime.now()
        with session_file.open("w") as f:
            for i in range(5000):
                entry = {
                    "type": "user" if i % 2 == 0 else "assistant",
                    "message": {"content": f"Message number {i} with some content padding " * 5},
                    "timestamp": (now + timedelta(seconds=i)).isoformat(),
                }
                f.write(json.dumps(entry) + "\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_invalid_since_date_format(self, runner: CliRunner, tmp_path: Path) -> None:
        """--since with invalid date format produces clean error."""
        result = runner.invoke(
            app, ["analyze", "--dir", str(tmp_path), "--since", "not-a-date"]
        )
        assert result.exit_code == 1
        assert "Invalid date format" in result.output
        assert "Traceback" not in result.output

    def test_since_date_various_bad_formats(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Various invalid date formats all produce clean errors."""
        bad_dates = ["2024/01/15", "Jan 15 2024", "15-01-2024", "yesterday"]
        for bad_date in bad_dates:
            result = runner.invoke(
                app, ["analyze", "--dir", str(tmp_path), "--since", bad_date]
            )
            assert result.exit_code == 1, f"Expected exit 1 for date '{bad_date}'"
            assert "Traceback" not in result.output

    def test_unsupported_format_option(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Unsupported --format value produces clean error."""
        result = runner.invoke(
            app, ["analyze", "--dir", str(tmp_path), "--format", "csv"]
        )
        assert result.exit_code == 1
        assert "Unsupported format" in result.output
        assert "Traceback" not in result.output

    def test_session_with_missing_timestamp_fields(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Session entries missing timestamp fields are handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        lines = [
            json.dumps({"type": "user", "message": {"content": "no timestamp here"}}),
            json.dumps({"type": "assistant", "message": {"content": "me neither"}}),
        ]
        (project_dir / "no_ts.jsonl").write_text("\n".join(lines) + "\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_session_with_null_content(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Session entries with null content fields are handled."""
        project_dir = tmp_path / ".claude" / "projects" / "test"
        project_dir.mkdir(parents=True)
        lines = [
            json.dumps({"type": "user", "message": None, "timestamp": "2024-01-15T10:00:00Z"}),
            json.dumps({"type": "assistant", "message": {"content": None}, "timestamp": "2024-01-15T10:00:01Z"}),
        ]
        (project_dir / "null_content.jsonl").write_text("\n".join(lines) + "\n")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_deeply_nested_source_directories(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Source directories with deep nesting don't crash."""
        # Claude projects with deeply nested path
        deep = tmp_path / ".claude" / "projects" / "a" / "b" / "c"
        deep.mkdir(parents=True)

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_invalid_since_e2e_no_traceback(self, tmp_path: Path) -> None:
        """E2E: invalid --since date produces no traceback."""
        result = _run_cli(
            "analyze", "--dir", str(tmp_path),
            "--since", "not-a-date",
            cwd=tmp_path,
        )
        _assert_no_traceback(result)
        assert result.returncode == 1

    def test_multiple_source_types_with_mixed_quality(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Mixed valid/invalid files across claude and codex sources."""
        # Valid Claude session
        claude_dir = tmp_path / ".claude" / "projects" / "test"
        claude_dir.mkdir(parents=True)
        now = datetime.now()
        (claude_dir / "good.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "hello"}, "timestamp": now.isoformat()}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "hi"}, "timestamp": now.isoformat()}) + "\n"
        )
        # Bad Claude session
        (claude_dir / "bad.jsonl").write_text("CORRUPT DATA\n")

        # Valid Codex session
        codex_dir = tmp_path / ".codex" / "sessions"
        codex_dir.mkdir(parents=True)
        (codex_dir / "rollout-good.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "codex hello"}, "timestamp": now.isoformat()}) + "\n"
        )
        # Bad Codex session
        (codex_dir / "rollout-bad.jsonl").write_text("{{{{{")

        result = runner.invoke(app, ["analyze", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# 6. --global flag: discovers sessions from mocked home directories
# ---------------------------------------------------------------------------
class TestGlobalFlagDiscovery:
    """Tests for --global flag discovering sessions from home directories."""

    def test_global_discovers_claude_sessions_from_home(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--global discovers .claude/ sessions from mocked home directory."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        project_dir = fake_home / ".claude" / "projects" / "home-project"
        project_dir.mkdir(parents=True)
        now = datetime.now()
        (project_dir / "session.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "home session"}, "timestamp": now.isoformat()}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "reply"}, "timestamp": now.isoformat()}) + "\n"
        )

        scan_dir = tmp_path / "project"
        scan_dir.mkdir()

        with patch("session_insights.cli.Path.home", return_value=fake_home):
            result = runner.invoke(
                app, ["sessions", "--dir", str(scan_dir), "--global"]
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sources"]["claude"] > 0

    def test_global_discovers_codex_sessions_from_home(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--global discovers .codex/ sessions from mocked home directory."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        codex_dir = fake_home / ".codex" / "sessions"
        codex_dir.mkdir(parents=True)
        now = datetime.now()
        (codex_dir / "rollout-home.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "codex home"}, "timestamp": now.isoformat()}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "reply"}, "timestamp": now.isoformat()}) + "\n"
        )

        scan_dir = tmp_path / "project"
        scan_dir.mkdir()

        with patch("session_insights.cli.Path.home", return_value=fake_home):
            result = runner.invoke(
                app, ["sessions", "--dir", str(scan_dir), "--global"]
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sources"]["codex"] > 0

    def test_global_with_no_home_claude_or_codex(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--global with empty home dir (no .claude/ or .codex/) exits cleanly."""
        fake_home = tmp_path / "empty_home"
        fake_home.mkdir()

        scan_dir = tmp_path / "project"
        scan_dir.mkdir()

        with patch("session_insights.cli.Path.home", return_value=fake_home):
            result = runner.invoke(
                app, ["sessions", "--dir", str(scan_dir), "--global"]
            )

        assert result.exit_code == 0
        assert "Traceback" not in result.output
        data = json.loads(result.output)
        assert data["session_count"] == 0

    def test_global_flag_with_analyze_command(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--global flag on analyze command with mocked home dir."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        project_dir = fake_home / ".claude" / "projects" / "home-project"
        project_dir.mkdir(parents=True)
        now = datetime.now()
        (project_dir / "session.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "analyze home"}, "timestamp": now.isoformat()}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "ok"}, "timestamp": now.isoformat()}) + "\n"
        )

        scan_dir = tmp_path / "project"
        scan_dir.mkdir()

        with patch("pathlib.Path.home", return_value=fake_home):
            result = runner.invoke(
                app, ["analyze", "--dir", str(scan_dir), "--global"]
            )

        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_global_combines_local_and_home_sessions(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--global finds sessions from both --dir and home directory."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        # Home has a Claude session
        home_project = fake_home / ".claude" / "projects" / "home-proj"
        home_project.mkdir(parents=True)
        now = datetime.now()
        (home_project / "session.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "from home"}, "timestamp": now.isoformat()}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "ok"}, "timestamp": now.isoformat()}) + "\n"
        )

        # Local dir also has a Claude session
        local_dir = tmp_path / "local"
        local_dir.mkdir()
        local_project = local_dir / ".claude" / "projects" / "local-proj"
        local_project.mkdir(parents=True)
        (local_project / "session.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "from local"}, "timestamp": now.isoformat()}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": "ok"}, "timestamp": now.isoformat()}) + "\n"
        )

        with patch("session_insights.cli.Path.home", return_value=fake_home):
            result = runner.invoke(
                app, ["sessions", "--dir", str(local_dir), "--global"]
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        # Should have sessions from both local and home
        assert data["session_count"] >= 2

    def test_global_no_global_default_ignores_home(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Without --global, sessions from home are NOT discovered."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        home_project = fake_home / ".claude" / "projects" / "home-proj"
        home_project.mkdir(parents=True)
        now = datetime.now()
        (home_project / "session.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "home only"}, "timestamp": now.isoformat()}) + "\n"
        )

        scan_dir = tmp_path / "empty_project"
        scan_dir.mkdir()

        with patch("session_insights.cli.Path.home", return_value=fake_home):
            result = runner.invoke(
                app, ["sessions", "--dir", str(scan_dir)]
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_count"] == 0
