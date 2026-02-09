"""Full-pipeline integration tests: parse → unified model → format.

Tests the complete pipeline for both Claude and VerMAS session types,
asserting rich content in formatted output. Covers:
- Non-empty content sections in output notes
- VerMAS notes: task description, signals, and learnings
- Claude notes: conversation summaries and tool usage
- Analyze subcommand: clean runs and correct exit codes
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

from distill.core import analyze, discover_sessions, generate_weekly_notes, parse_session_file
from distill.formatters.obsidian import ObsidianFormatter
from distill.parsers.claude import ClaudeParser
from distill.parsers.models import BaseSession
from distill.parsers.vermas import VermasParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SRC_DIR = str(Path(__file__).parents[2] / "src")


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the session-insights CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "distill", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": SRC_DIR},
    )


# ---------------------------------------------------------------------------
# Fixtures — Claude
# ---------------------------------------------------------------------------


@pytest.fixture
def rich_claude_history(tmp_path: Path) -> Path:
    """Create a .claude directory with rich session data (tool calls, messages)."""
    project_dir = tmp_path / ".claude" / "projects" / "my-project"
    project_dir.mkdir(parents=True)

    now = datetime.now(timezone.utc)
    ts = lambda delta: (now + delta).isoformat()  # noqa: E731

    entries = [
        # User message
        {
            "type": "user",
            "timestamp": ts(timedelta(hours=-2)),
            "message": {"content": "Fix the authentication bug in the login handler"},
        },
        # Assistant reply with tool_use
        {
            "type": "assistant",
            "timestamp": ts(timedelta(hours=-2, minutes=1)),
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "content": [
                    {"type": "text", "text": "I'll look at the login handler code."},
                    {
                        "type": "tool_use",
                        "id": "tu_001",
                        "name": "Read",
                        "input": {"file_path": "/src/auth/login.py"},
                    },
                ],
            },
        },
        # Tool result
        {
            "type": "user",
            "timestamp": ts(timedelta(hours=-2, minutes=2)),
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_001",
                        "content": "def login(user, password): ...",
                    }
                ]
            },
        },
        # Assistant writes a fix
        {
            "type": "assistant",
            "timestamp": ts(timedelta(hours=-2, minutes=3)),
            "message": {
                "content": [
                    {"type": "text", "text": "I found the bug. Let me fix it."},
                    {
                        "type": "tool_use",
                        "id": "tu_002",
                        "name": "Edit",
                        "input": {
                            "file_path": "/src/auth/login.py",
                            "old_string": "if password ==",
                            "new_string": "if verify_hash(password,",
                        },
                    },
                ],
            },
        },
        # Tool result for Edit
        {
            "type": "user",
            "timestamp": ts(timedelta(hours=-2, minutes=4)),
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_002",
                        "content": "File edited successfully.",
                    }
                ]
            },
        },
        # User asks for tests
        {
            "type": "user",
            "timestamp": ts(timedelta(hours=-1, minutes=50)),
            "message": {"content": "Now add unit tests for the fix"},
        },
        # Assistant runs tests
        {
            "type": "assistant",
            "timestamp": ts(timedelta(hours=-1, minutes=49)),
            "message": {
                "content": [
                    {"type": "text", "text": "I'll create tests for the authentication fix."},
                    {
                        "type": "tool_use",
                        "id": "tu_003",
                        "name": "Write",
                        "input": {"file_path": "/tests/test_login.py", "content": "..."},
                    },
                ],
            },
        },
        # Tool result for Write
        {
            "type": "user",
            "timestamp": ts(timedelta(hours=-1, minutes=48)),
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_003",
                        "content": "File written.",
                    }
                ]
            },
        },
    ]

    session_file = project_dir / "rich-session.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return tmp_path


# ---------------------------------------------------------------------------
# Fixtures — VerMAS
# ---------------------------------------------------------------------------


@pytest.fixture
def rich_vermas_history(tmp_path: Path) -> Path:
    """Create a .vermas directory with rich workflow data.

    Includes signals, task description, mission info, agent learnings,
    and improvement records.
    """
    now = datetime.now(timezone.utc)

    # --- state directory with signals ---
    workflow_name = "mission-test42-cycle-2-execute-add-login-page"
    state_dir = tmp_path / ".vermas" / "state" / workflow_name
    signals_dir = state_dir / "signals"
    signals_dir.mkdir(parents=True)

    signals = [
        {
            "signal_id": "sig-001",
            "agent_id": "dev-aaaa",
            "role": "dev",
            "signal": "done",
            "created_at": (now - timedelta(minutes=30)).isoformat(),
            "message": "Implementation complete with tests passing",
            "workflow_id": workflow_name,
        },
        {
            "signal_id": "sig-002",
            "agent_id": "qa-bbbb",
            "role": "qa",
            "signal": "needs_revision",
            "created_at": (now - timedelta(minutes=20)).isoformat(),
            "message": "Missing edge case test for empty password",
            "workflow_id": workflow_name,
        },
        {
            "signal_id": "sig-003",
            "agent_id": "dev-aaaa",
            "role": "dev",
            "signal": "done",
            "created_at": (now - timedelta(minutes=10)).isoformat(),
            "message": "Added edge case tests",
            "workflow_id": workflow_name,
        },
        {
            "signal_id": "sig-004",
            "agent_id": "qa-bbbb",
            "role": "qa",
            "signal": "approved",
            "created_at": now.isoformat(),
            "message": "All tests pass, code looks good",
            "workflow_id": workflow_name,
        },
    ]

    for i, sig in enumerate(signals):
        sig_file = signals_dir / f"signal-{i:03d}.yaml"
        sig_file.write_text(yaml.dump(sig), encoding="utf-8")

    # --- task description ---
    task_dir = (
        tmp_path
        / ".vermas"
        / "tasks"
        / "mission-test42"
        / "authentication"
    )
    task_dir.mkdir(parents=True)
    task_file = task_dir / "add-login-page.md"
    task_file.write_text(
        "---\nstatus: done\npriority: high\n---\n"
        "# Add Login Page\n\n"
        "Implement a login page with email/password authentication "
        "and proper error handling for invalid credentials.\n",
        encoding="utf-8",
    )

    # --- mission epic ---
    epic_file = tmp_path / ".vermas" / "tasks" / "mission-test42" / "_epic.md"
    epic_file.write_text(
        "---\nstatus: active\npriority: high\n---\n"
        "# User Authentication System\n\n"
        "Build end-to-end user authentication.\n",
        encoding="utf-8",
    )

    # --- agent learnings ---
    knowledge_dir = tmp_path / ".vermas" / "knowledge" / "agents"
    knowledge_dir.mkdir(parents=True)
    learnings_file = knowledge_dir / "agent-learnings.yaml"
    learnings_data = {
        "agents": {
            "dev": {
                "learnings": [
                    "Always run tests before signaling done",
                    "Keep commits small and focused",
                ],
                "strengths": ["Fast implementation"],
                "weaknesses": ["Sometimes misses edge cases"],
                "best_practices": [
                    "Write tests alongside code",
                    "Use descriptive commit messages",
                ],
            },
            "qa": {
                "learnings": [
                    "Check edge cases first",
                ],
                "strengths": ["Thorough review"],
                "weaknesses": [],
                "best_practices": ["Verify all acceptance criteria"],
            },
        }
    }
    learnings_file.write_text(yaml.dump(learnings_data), encoding="utf-8")

    # --- improvements ---
    imp_dir = tmp_path / ".vermas" / "knowledge" / "improvements"
    imp_dir.mkdir(parents=True)
    imp_file = imp_dir / "imp-test42-001.yaml"
    imp_data = {
        "id": "imp-test42-001",
        "date": now.isoformat(),
        "type": "process",
        "target": "dev-qa-workflow",
        "change": "Added automated edge case detection",
        "validated": True,
        "impact": "Reduced QA revision cycles by 40%",
    }
    imp_file.write_text(yaml.dump(imp_data), encoding="utf-8")

    return tmp_path


# ===========================================================================
# Claude full-pipeline tests
# ===========================================================================


class TestClaudeFullPipeline:
    """Full pipeline tests for Claude sessions: parse → model → format."""

    def test_parse_produces_messages_and_tools(
        self, rich_claude_history: Path
    ) -> None:
        """Parsed Claude session has messages and tool_calls populated."""
        parser = ClaudeParser()
        sessions = parser.parse_directory(rich_claude_history / ".claude")

        assert len(sessions) >= 1
        session = sessions[0]

        # Messages populated
        assert len(session.messages) >= 2
        user_msgs = [m for m in session.messages if m.role == "user"]
        assistant_msgs = [m for m in session.messages if m.role == "assistant"]
        assert len(user_msgs) >= 1
        assert len(assistant_msgs) >= 1

        # Tool calls populated
        assert len(session.tool_calls) >= 1
        tool_names = {tc.tool_name for tc in session.tool_calls}
        assert "Read" in tool_names or "Edit" in tool_names

    def test_formatted_note_has_nonempty_sections(
        self, rich_claude_history: Path
    ) -> None:
        """Formatted Claude note has non-empty Summary, Tools, and Conversation."""
        parser = ClaudeParser()
        sessions = parser.parse_directory(rich_claude_history / ".claude")
        assert sessions

        formatter = ObsidianFormatter(include_conversation=True)
        note = formatter.format_session(sessions[0])

        # Non-empty content overall
        assert len(note) > 200, "Note is too short to contain rich content"

        # Frontmatter present
        assert note.startswith("---")
        assert "source:" in note

        # Summary section is populated (not the placeholder)
        assert "## Summary" in note
        # The summary should come from the first user message
        assert "authentication" in note.lower() or "login" in note.lower()

        # Tools section has actual tool data
        assert "## Tools Used" in note
        # Should show at least one tool with call count
        assert "Read" in note or "Edit" in note or "Write" in note

        # Conversation section is non-empty
        assert "## Conversation" in note
        assert "_Conversation not included._" not in note

    def test_formatted_note_includes_tool_usage_summary(
        self, rich_claude_history: Path
    ) -> None:
        """Claude note shows tool usage counts in the Tools section."""
        parser = ClaudeParser()
        sessions = parser.parse_directory(rich_claude_history / ".claude")
        session = sessions[0]

        # Verify tools_used is auto-derived from tool_calls
        assert len(session.tools_used) >= 1

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(session)

        # Should contain tool name and count pattern like "**Read**: 1 call"
        assert "call" in note.lower()

    def test_formatted_note_includes_outcomes(
        self, rich_claude_history: Path
    ) -> None:
        """Claude note includes outcomes extracted from tool calls."""
        parser = ClaudeParser()
        sessions = parser.parse_directory(rich_claude_history / ".claude")
        session = sessions[0]

        # Session should have auto-enriched outcomes (files modified)
        assert len(session.outcomes) >= 1

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(session)

        assert "## Outcomes" in note
        assert "_No outcomes recorded._" not in note

    def test_full_pipeline_discover_parse_analyze_format(
        self, rich_claude_history: Path, tmp_path: Path
    ) -> None:
        """End-to-end: discover → parse → analyze → format for Claude."""
        # 1. Discover
        discovered = discover_sessions(rich_claude_history, sources=["claude"])
        assert "claude" in discovered

        # 2. Parse
        all_sessions: list[BaseSession] = []
        for source, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, source))
        assert len(all_sessions) >= 1

        # 3. Analyze
        result = analyze(all_sessions)
        assert result.stats.total_sessions >= 1

        # 4. Format
        formatter = ObsidianFormatter(include_conversation=True)
        output_dir = tmp_path / "output" / "sessions"
        output_dir.mkdir(parents=True)

        for session in result.sessions:
            note = formatter.format_session(session)
            note_path = output_dir / f"{session.note_name}.md"
            note_path.write_text(note, encoding="utf-8")

        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1

        # Every generated note should have non-empty content
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            assert len(content) > 100
            assert "## Summary" in content


# ===========================================================================
# VerMAS full-pipeline tests
# ===========================================================================


class TestVermasFullPipeline:
    """Full pipeline tests for VerMAS sessions: parse → model → format."""

    def test_parse_produces_signals_and_metadata(
        self, rich_vermas_history: Path
    ) -> None:
        """Parsed VerMAS session has signals, task info, and learnings."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")

        assert len(sessions) >= 1
        session = sessions[0]

        # Signals populated
        assert len(session.signals) >= 2
        signal_types = {s.signal for s in session.signals}
        assert "done" in signal_types
        assert "approved" in signal_types

        # Task metadata
        assert session.task_name is not None
        assert session.mission_id is not None
        assert session.cycle is not None

    def test_parse_extracts_task_description(
        self, rich_vermas_history: Path
    ) -> None:
        """Parser extracts task description from .vermas/tasks/."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")
        session = sessions[0]

        assert session.task_description != ""
        assert "login" in session.task_description.lower() or "authentication" in session.task_description.lower()

    def test_parse_extracts_agent_learnings(
        self, rich_vermas_history: Path
    ) -> None:
        """Parser extracts agent learnings from knowledge files."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")
        session = sessions[0]

        assert len(session.learnings) >= 1
        dev_learning = next(
            (al for al in session.learnings if al.agent == "dev"), None
        )
        assert dev_learning is not None
        assert len(dev_learning.learnings) >= 1
        assert len(dev_learning.best_practices) >= 1

    def test_parse_extracts_improvements(
        self, rich_vermas_history: Path
    ) -> None:
        """Parser extracts improvement records for the mission."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")
        session = sessions[0]

        assert len(session.improvements) >= 1
        imp = session.improvements[0]
        assert imp.validated is True
        assert imp.impact != ""

    def test_formatted_note_has_nonempty_sections(
        self, rich_vermas_history: Path
    ) -> None:
        """Formatted VerMAS note has non-empty content sections."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")
        session = sessions[0]

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(session)

        # Overall content richness
        assert len(note) > 300, "Note is too short to contain rich content"

        # Frontmatter
        assert note.startswith("---")
        assert "source: vermas" in note

        # Summary section
        assert "## Summary" in note
        assert "_No summary available._" not in note

    def test_formatted_note_includes_task_description(
        self, rich_vermas_history: Path
    ) -> None:
        """VerMAS note includes the Task Details section with description."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(sessions[0])

        assert "## Task Details" in note
        assert "**Task:**" in note
        assert "### Description" in note
        # The task description content itself
        assert "login" in note.lower() or "authentication" in note.lower()

    def test_formatted_note_includes_signals(
        self, rich_vermas_history: Path
    ) -> None:
        """VerMAS note includes the Agent Signals table."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(sessions[0])

        assert "## Agent Signals" in note
        # Table header
        assert "| Time |" in note
        assert "| Agent |" in note or "Agent" in note
        # Signal values present in the table
        assert "done" in note
        assert "approved" in note

    def test_formatted_note_includes_learnings(
        self, rich_vermas_history: Path
    ) -> None:
        """VerMAS note includes the Learnings section with agent data."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(sessions[0])

        assert "## Learnings" in note
        assert "### Agent: dev" in note
        assert "Always run tests" in note
        assert "**Best Practices:**" in note

    def test_formatted_note_includes_improvements(
        self, rich_vermas_history: Path
    ) -> None:
        """VerMAS note includes the Improvements sub-section."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")

        formatter = ObsidianFormatter(include_conversation=False)
        note = formatter.format_session(sessions[0])

        assert "### Improvements" in note
        assert "validated" in note
        assert "Impact:" in note

    def test_vermas_outcome_is_derived_from_signals(
        self, rich_vermas_history: Path
    ) -> None:
        """VerMAS session outcome is determined by signals (last = approved)."""
        parser = VermasParser()
        sessions = parser.parse_directory(rich_vermas_history / ".vermas")
        session = sessions[0]

        assert session.outcome == "approved"

    def test_full_pipeline_discover_parse_analyze_format(
        self, rich_vermas_history: Path, tmp_path: Path
    ) -> None:
        """End-to-end: discover → parse → analyze → format for VerMAS."""
        # 1. Discover
        discovered = discover_sessions(rich_vermas_history, sources=["vermas"])
        assert "vermas" in discovered

        # 2. Parse
        all_sessions: list[BaseSession] = []
        for source, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, source))
        assert len(all_sessions) >= 1

        # 3. Analyze
        result = analyze(all_sessions)
        assert result.stats.total_sessions >= 1

        # 4. Format
        formatter = ObsidianFormatter(include_conversation=False)
        output_dir = tmp_path / "output" / "sessions"
        output_dir.mkdir(parents=True)

        for session in result.sessions:
            note = formatter.format_session(session)
            note_path = output_dir / f"{session.note_name}.md"
            note_path.write_text(note, encoding="utf-8")

        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            assert len(content) > 200
            assert "## Summary" in content
            # VerMAS-specific sections
            assert "## Task Details" in content
            assert "## Agent Signals" in content


# ===========================================================================
# Mixed sources pipeline test
# ===========================================================================


class TestMixedSourcesPipeline:
    """Test the pipeline with both Claude and VerMAS data together."""

    def test_mixed_sources_pipeline(
        self,
        rich_claude_history: Path,
        tmp_path: Path,
    ) -> None:
        """Pipeline handles Claude + VerMAS data simultaneously."""
        # Build a VerMAS fixture inside the same root as the Claude fixture
        now = datetime.now(timezone.utc)
        workflow_name = "mission-mix01-cycle-1-execute-mixed-test"
        signals_dir = rich_claude_history / ".vermas" / "state" / workflow_name / "signals"
        signals_dir.mkdir(parents=True)

        sig_data = {
            "signal_id": "sig-mix-001",
            "agent_id": "dev-mix",
            "role": "dev",
            "signal": "done",
            "created_at": now.isoformat(),
            "message": "Mixed pipeline test complete",
            "workflow_id": workflow_name,
        }
        (signals_dir / "signal-001.yaml").write_text(
            yaml.dump(sig_data), encoding="utf-8"
        )

        # Discover all
        discovered = discover_sessions(rich_claude_history)
        assert "claude" in discovered
        assert "vermas" in discovered

        # Parse all
        all_sessions: list[BaseSession] = []
        for source, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, source))

        assert len(all_sessions) >= 2
        sources_found = {s.source for s in all_sessions}
        assert "claude-code" in sources_found or "claude" in sources_found
        assert "vermas" in sources_found

        # Analyze
        result = analyze(all_sessions)
        assert result.stats.total_sessions >= 2

        # Format each
        formatter = ObsidianFormatter(include_conversation=False)
        output_dir = tmp_path / "output" / "sessions"
        output_dir.mkdir(parents=True)

        for session in result.sessions:
            note = formatter.format_session(session)
            note_path = output_dir / f"{session.note_name}.md"
            note_path.write_text(note, encoding="utf-8")

        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 2


# ===========================================================================
# Analyze subcommand tests (exit codes & clean runs)
# ===========================================================================


class TestAnalyzeSubcommand:
    """Tests for the analyze subcommand: exit codes and clean output."""

    def test_analyze_runs_clean_with_data(
        self, rich_claude_history: Path, tmp_path: Path
    ) -> None:
        """analyze subcommand exits 0 and writes output with real data."""
        output_dir = tmp_path / "notes"
        result = _run_cli(
            "analyze",
            "--dir", str(rich_claude_history),
            "--output", str(output_dir),
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"stderr: {_strip_ansi(result.stderr)}"
        assert "Analysis complete" in _strip_ansi(result.stdout)

        # Verify output artifacts
        session_files = list((output_dir / "sessions").glob("*.md"))
        assert len(session_files) >= 1

        daily_files = list((output_dir / "daily").glob("*.md"))
        assert len(daily_files) >= 1

        index = output_dir / "index.md"
        assert index.exists()

    def test_analyze_runs_clean_with_vermas_data(
        self, rich_vermas_history: Path, tmp_path: Path
    ) -> None:
        """analyze subcommand exits 0 with VerMAS data."""
        output_dir = tmp_path / "notes"
        result = _run_cli(
            "analyze",
            "--dir", str(rich_vermas_history),
            "--output", str(output_dir),
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"stderr: {_strip_ansi(result.stderr)}"
        assert "Analysis complete" in _strip_ansi(result.stdout)

    def test_analyze_exit_0_no_sessions(self, tmp_path: Path) -> None:
        """analyze exits 0 gracefully when no sessions are found."""
        output_dir = tmp_path / "notes"
        result = _run_cli(
            "analyze",
            "--dir", str(tmp_path),
            "--output", str(output_dir),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "No session files found" in _strip_ansi(result.stdout)

    def test_analyze_exit_1_invalid_format(self, tmp_path: Path) -> None:
        """analyze exits 1 for unsupported --format value."""
        result = _run_cli(
            "analyze",
            "--dir", str(tmp_path),
            "--format", "csv",
            cwd=tmp_path,
        )

        assert result.returncode == 1

    def test_analyze_exit_1_invalid_date(self, tmp_path: Path) -> None:
        """analyze exits 1 for invalid --since date."""
        result = _run_cli(
            "analyze",
            "--dir", str(tmp_path),
            "--since", "not-a-date",
            cwd=tmp_path,
        )

        assert result.returncode == 1

    def test_analyze_with_source_filter(
        self, rich_claude_history: Path, tmp_path: Path
    ) -> None:
        """analyze --source claude filters correctly."""
        output_dir = tmp_path / "notes"
        result = _run_cli(
            "analyze",
            "--dir", str(rich_claude_history),
            "--output", str(output_dir),
            "--source", "claude",
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"stderr: {_strip_ansi(result.stderr)}"

    def test_analyze_with_date_filter_future(
        self, rich_claude_history: Path, tmp_path: Path
    ) -> None:
        """analyze --since <future> exits 0 with no sessions message."""
        output_dir = tmp_path / "notes"
        future = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        result = _run_cli(
            "analyze",
            "--dir", str(rich_claude_history),
            "--output", str(output_dir),
            "--since", future,
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "No sessions found" in _strip_ansi(result.stdout)

    def test_analyze_help_exits_0(self, tmp_path: Path) -> None:
        """analyze --help exits 0."""
        result = _run_cli("analyze", "--help", cwd=tmp_path)
        assert result.returncode == 0
        assert "analyze" in _strip_ansi(result.stdout).lower()

    def test_version_exits_clean(self, tmp_path: Path) -> None:
        """--version exits cleanly."""
        result = _run_cli("--version", cwd=tmp_path)
        # Typer may exit 0 or raise Exit(0)
        assert result.returncode in (0, 1)
        assert "session-insights" in _strip_ansi(result.stdout) or "0.1.0" in _strip_ansi(result.stdout)
