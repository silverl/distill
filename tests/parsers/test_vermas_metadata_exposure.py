"""Tests for VerMAS metadata exposure through BaseSession.

Validates that all VerMAS task metadata is fully exposed through the unified
BaseSession model to downstream consumers (formatters, measurers).

Covers: task_description, signals, learnings, improvements, cycle_info,
quality_rating — with edge cases for missing fields and older formats.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from session_insights.formatters.obsidian import ObsidianFormatter
from session_insights.parsers.models import (
    AgentLearning,
    AgentSignal,
    CycleInfo,
    KnowledgeImprovement,
)
from session_insights.parsers.vermas import (
    VermasParser,
    VermasSession,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal_yaml(
    signal_id: str,
    role: str,
    signal: str,
    message: str,
    workflow_id: str,
    created_at: str,
    agent_id: str | None = None,
) -> dict:
    """Build a signal YAML dict."""
    return {
        "signal_id": signal_id,
        "agent_id": agent_id or f"{role}01",
        "role": role,
        "signal": signal,
        "message": message,
        "workflow_id": workflow_id,
        "created_at": created_at,
    }


def _write_signal(signals_dir: Path, data: dict) -> None:
    """Write a signal YAML file."""
    (signals_dir / f"{data['signal_id']}.yaml").write_text(yaml.dump(data))


def _create_full_vermas_dir(base: Path) -> Path:
    """Create a fully-populated .vermas directory for testing.

    Returns the .vermas directory path.
    """
    vermas_dir = base / ".vermas"

    # Workflow with full metadata
    wf_id = "mission-abc123-cycle-3-execute-implement-auth"
    wf_dir = vermas_dir / "state" / wf_id
    sig_dir = wf_dir / "signals"
    sig_dir.mkdir(parents=True)

    signals = [
        _make_signal_yaml("s1", "dev", "done", "Implementation complete", wf_id, "2024-06-15T10:00:00"),
        _make_signal_yaml("s2", "qa", "needs_revision", "Fix edge case", wf_id, "2024-06-15T10:15:00"),
        _make_signal_yaml("s3", "dev", "done", "Fixed edge case", wf_id, "2024-06-15T10:30:00"),
        _make_signal_yaml("s4", "qa", "approved", "All tests pass", wf_id, "2024-06-15T10:45:00"),
    ]
    for sig in signals:
        _write_signal(sig_dir, sig)

    # Task description file
    task_dir = vermas_dir / "tasks" / "mission-abc123" / "auth"
    task_dir.mkdir(parents=True)
    (task_dir / "implement-auth.md").write_text(
        "---\nstatus: done\n---\n# Implement Auth\n\nAdd JWT authentication to the API.\n"
    )

    # Mission epic
    mission_dir = vermas_dir / "tasks" / "mission-abc123"
    (mission_dir / "_epic.md").write_text(
        "---\nstatus: in_progress\npriority: high\n---\n# Auth Mission\n\nBuild authentication system.\n"
    )

    # Agent learnings
    agents_dir = vermas_dir / "knowledge" / "agents"
    agents_dir.mkdir(parents=True)
    learnings = {
        "agents": {
            "dev": {
                "learnings": ["Test-driven development works well"],
                "strengths": ["Quick iteration"],
                "weaknesses": ["Missing edge cases"],
                "best_practices": ["Always write tests first"],
            },
            "qa": {
                "learnings": ["Check boundary conditions"],
                "strengths": ["Thorough testing"],
                "weaknesses": [],
                "best_practices": ["Run full suite before approval"],
            },
        }
    }
    (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings))

    # Improvements
    imp_dir = vermas_dir / "knowledge" / "improvements"
    imp_dir.mkdir(parents=True)
    imp_data = {
        "id": "adapt-mission-abc123-c3-dev",
        "date": "2024-06-15T10:00:00",
        "type": "prompt",
        "target": "agent/dev",
        "change": "Added error handling instructions",
        "before_metrics": {"success_rate": 0.6},
        "after_metrics": {"success_rate": 0.9},
        "validated": True,
        "impact": "positive: 60% -> 90%",
    }
    (imp_dir / "adapt-mission-abc123-c3-dev.yaml").write_text(yaml.dump(imp_data))

    return vermas_dir


# ---------------------------------------------------------------------------
# Task Description Tests
# ---------------------------------------------------------------------------

class TestTaskDescriptionExposure:
    """Tests that task_description is always populated."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_task_description_from_task_file(self, parser: VermasParser) -> None:
        """Task description populated from task markdown file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert "JWT authentication" in sessions[0].task_description

    def test_task_description_fallback_to_mission_description(self, parser: VermasParser) -> None:
        """When no task file exists, fall back to mission description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Workflow with no task file
            wf_id = "mission-xyz-cycle-1-execute-missing-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            # Mission epic (provides fallback description)
            mission_dir = vermas_dir / "tasks" / "mission-xyz"
            mission_dir.mkdir(parents=True)
            (mission_dir / "_epic.md").write_text(
                "# XYZ Mission\n\nFallback description from epic.\n"
            )

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].task_description == "Fallback description from epic."

    def test_task_description_fallback_to_task_name(self, parser: VermasParser) -> None:
        """When no task file or mission description exists, derive from task name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Workflow with no task file and no mission info
            wf_id = "mission-orphan-cycle-1-execute-fix-login-bug"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].task_description == "Fix login bug"

    def test_task_description_accessible_in_formatter(self, parser: VermasParser) -> None:
        """Formatter can access task_description and render it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])
            assert "### Description" in note
            assert "JWT authentication" in note

    def test_task_description_fallback_renders_in_formatter(self, parser: VermasParser) -> None:
        """Fallback task_description renders in formatter output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-render-cycle-1-execute-add-feature"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])
            assert "### Description" in note
            assert "Add feature" in note


# ---------------------------------------------------------------------------
# Signals Tests
# ---------------------------------------------------------------------------

class TestSignalsExposure:
    """Tests that all signal types are exposed with timestamps."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_all_signal_types_preserved(self, parser: VermasParser) -> None:
        """All signal types (done, approved, needs_revision) are captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            signal_types = {s.signal for s in sessions[0].signals}
            assert "done" in signal_types
            assert "approved" in signal_types
            assert "needs_revision" in signal_types

    def test_signals_have_timestamps(self, parser: VermasParser) -> None:
        """All signals have valid timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            for signal in sessions[0].signals:
                assert signal.timestamp is not None
                assert isinstance(signal.timestamp, datetime)

    def test_signals_sorted_by_timestamp(self, parser: VermasParser) -> None:
        """Signals are sorted chronologically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            timestamps = [s.timestamp for s in sessions[0].signals]
            assert timestamps == sorted(timestamps)

    def test_signals_include_agent_metadata(self, parser: VermasParser) -> None:
        """Signals include agent_id, role, and message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            for signal in sessions[0].signals:
                assert signal.agent_id != ""
                assert signal.role in ("dev", "qa")
                assert isinstance(signal.message, str)

    def test_signals_accessible_in_formatter(self, parser: VermasParser) -> None:
        """Formatter can render signals timeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])
            assert "## Agent Signals" in note
            assert "done" in note
            assert "approved" in note
            assert "needs_revision" in note

    def test_blocked_signal_captured(self, parser: VermasParser) -> None:
        """Blocked signals are properly captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-blk-cycle-1-execute-blocked-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "blocked", "Dependency unavailable", wf_id, "2024-01-15T10:00:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].signals[0].signal == "blocked"
            assert "Dependency unavailable" in sessions[0].signals[0].message

    def test_progress_signal_captured(self, parser: VermasParser) -> None:
        """Progress signals are properly captured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-prg-cycle-1-execute-slow-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "progress", "50% done", wf_id, "2024-01-15T10:00:00"
            ))
            _write_signal(sig_dir, _make_signal_yaml(
                "s2", "dev", "done", "Complete", wf_id, "2024-01-15T10:30:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            signal_types = [s.signal for s in sessions[0].signals]
            assert "progress" in signal_types
            assert "done" in signal_types


# ---------------------------------------------------------------------------
# Learnings Tests
# ---------------------------------------------------------------------------

class TestLearningsExposure:
    """Tests that learnings are populated from knowledge files."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_learnings_populated(self, parser: VermasParser) -> None:
        """Learnings array is populated from agent-learnings.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions[0].learnings) == 2
            agents = {l.agent for l in sessions[0].learnings}
            assert "dev" in agents
            assert "qa" in agents

    def test_learnings_include_all_fields(self, parser: VermasParser) -> None:
        """Each learning record includes learnings, strengths, weaknesses, best_practices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            dev_learning = next(l for l in sessions[0].learnings if l.agent == "dev")
            assert len(dev_learning.learnings) > 0
            assert len(dev_learning.strengths) > 0
            assert len(dev_learning.weaknesses) > 0
            assert len(dev_learning.best_practices) > 0

    def test_learnings_accessible_in_formatter(self, parser: VermasParser) -> None:
        """Formatter renders learnings section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])
            assert "## Learnings" in note
            assert "Agent: dev" in note
            assert "Best Practices" in note

    def test_missing_learnings_file(self, parser: VermasParser) -> None:
        """Learnings array is empty when no learnings file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-nol-cycle-1-execute-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].learnings == []

    def test_learnings_with_null_values(self, parser: VermasParser) -> None:
        """Handles learnings files with null/None values gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-null-cycle-1-execute-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            agents_dir = vermas_dir / "knowledge" / "agents"
            agents_dir.mkdir(parents=True)
            learnings_data = {
                "agents": {
                    "dev": {
                        "learnings": None,
                        "strengths": None,
                        "weaknesses": None,
                        "best_practices": None,
                    }
                }
            }
            (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].learnings) == 1
            assert sessions[0].learnings[0].learnings == []
            assert sessions[0].learnings[0].strengths == []


# ---------------------------------------------------------------------------
# Improvements Tests
# ---------------------------------------------------------------------------

class TestImprovementsExposure:
    """Tests that improvements are populated from knowledge files."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_improvements_populated(self, parser: VermasParser) -> None:
        """Improvements array is populated from knowledge/improvements files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions[0].improvements) == 1
            assert sessions[0].improvements[0].validated is True
            assert "error handling" in sessions[0].improvements[0].change

    def test_improvements_include_metrics(self, parser: VermasParser) -> None:
        """Improvements include before/after metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            imp = sessions[0].improvements[0]
            assert imp.before_metrics.get("success_rate") == 0.6
            assert imp.after_metrics.get("success_rate") == 0.9
            assert imp.impact != ""

    def test_improvements_accessible_in_formatter(self, parser: VermasParser) -> None:
        """Formatter renders improvements in learnings section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])
            assert "### Improvements" in note
            assert "validated" in note

    def test_no_improvements_for_unknown_mission(self, parser: VermasParser) -> None:
        """No improvements loaded when mission has no improvement files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-noimp-cycle-1-execute-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].improvements == []


# ---------------------------------------------------------------------------
# Cycle Info Tests
# ---------------------------------------------------------------------------

class TestCycleInfoExposure:
    """Tests that cycle_info is always available with cycle number and quality."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_cycle_info_populated(self, parser: VermasParser) -> None:
        """Cycle info is auto-derived from VerMAS fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            ci = sessions[0].cycle_info
            assert ci is not None
            assert ci.mission_id == "abc123"
            assert ci.cycle == 3
            assert ci.task_name == "implement-auth"
            assert ci.outcome == "approved"

    def test_cycle_info_has_quality_rating(self, parser: VermasParser) -> None:
        """Cycle info includes quality rating derived from outcome."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            ci = sessions[0].cycle_info
            assert ci is not None
            assert ci.quality_rating is not None
            # Approved with needs_revision => "good"
            assert ci.quality_rating == "good"

    def test_cycle_info_quality_excellent(self, parser: VermasParser) -> None:
        """Approved without revisions gets 'excellent' rating."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-exc-cycle-1-execute-clean-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))
            _write_signal(sig_dir, _make_signal_yaml(
                "s2", "qa", "approved", "LGTM", wf_id, "2024-01-15T10:15:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert sessions[0].cycle_info.quality_rating == "excellent"

    def test_cycle_info_quality_fair_for_needs_revision(self, parser: VermasParser) -> None:
        """needs_revision only outcome gets 'fair' rating."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-fair-cycle-1-execute-buggy-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "qa", "needs_revision", "Fix bugs", wf_id, "2024-01-15T10:00:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert sessions[0].cycle_info.quality_rating == "fair"

    def test_cycle_info_quality_poor_for_blocked(self, parser: VermasParser) -> None:
        """Blocked outcome gets 'poor' rating."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-poor-cycle-1-execute-stuck-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "blocked", "Stuck", wf_id, "2024-01-15T10:00:00"
            ))
            sessions = parser.parse_directory(vermas_dir)
            assert sessions[0].cycle_info.quality_rating == "poor"

    def test_cycle_info_accessible_in_formatter(self, parser: VermasParser) -> None:
        """Formatter renders cycle info including quality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])
            assert "**Cycle:** 3" in note
            assert "**Quality:** good" in note

    def test_cycle_info_model_direct(self) -> None:
        """CycleInfo model stores quality_rating."""
        ci = CycleInfo(
            mission_id="test",
            cycle=5,
            outcome="completed",
            quality_rating="excellent",
        )
        assert ci.quality_rating == "excellent"
        assert ci.cycle == 5


# ---------------------------------------------------------------------------
# Edge Cases: Missing Fields / Older Formats
# ---------------------------------------------------------------------------

class TestMetadataEdgeCases:
    """Edge cases for metadata exposure."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_older_format_no_learnings_directory(self, parser: VermasParser) -> None:
        """Handles older format where knowledge directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-old-cycle-1-execute-legacy-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].learnings == []
            assert sessions[0].improvements == []
            # task_description should still be derived from task_name
            assert sessions[0].task_description == "Legacy task"

    def test_older_format_no_tasks_directory(self, parser: VermasParser) -> None:
        """Handles older format without tasks directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-notask-cycle-2-execute-simple-fix"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].task_description == "Simple fix"
            assert sessions[0].mission_info is None
            assert sessions[0].recaps == []

    def test_session_with_single_signal(self, parser: VermasParser) -> None:
        """Session with only one signal still exposes all metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-one-cycle-1-execute-quick-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            sessions = parser.parse_directory(vermas_dir)
            session = sessions[0]
            assert session.cycle_info is not None
            assert session.cycle_info.cycle == 1
            assert session.task_description != ""
            assert len(session.signals) == 1

    def test_all_metadata_on_base_session(self, parser: VermasParser) -> None:
        """All metadata fields are accessible as BaseSession fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            session = sessions[0]

            # All these should be accessible on BaseSession
            assert session.task_description != ""
            assert len(session.signals) > 0
            assert len(session.learnings) > 0
            assert len(session.improvements) > 0
            assert session.cycle_info is not None
            assert session.cycle_info.quality_rating is not None

    def test_formatter_produces_all_vermas_sections(self, parser: VermasParser) -> None:
        """Full session produces all 4 required note sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])

            # All required sections from KPI measurer
            assert "### Description" in note
            assert "## Agent Signals" in note
            assert "## Learnings" in note
            assert "**Cycle:**" in note

    def test_events_log_signals_exposed(self, parser: VermasParser) -> None:
        """Signals from events.log (older format) are fully exposed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import json

            vermas_dir = Path(tmpdir) / ".vermas"
            wf_id = "mission-evt-cycle-1-execute-event-task"
            wf_dir = vermas_dir / "state" / wf_id
            wf_dir.mkdir(parents=True)

            events = [
                {
                    "type": "signal",
                    "timestamp": "2024-01-15T10:00:00",
                    "signal_id": "e1",
                    "agent_id": "dev01",
                    "role": "dev",
                    "signal": "done",
                    "message": "Implementation complete",
                    "workflow_id": wf_id,
                },
                {
                    "type": "signal",
                    "timestamp": "2024-01-15T10:30:00",
                    "signal_id": "e2",
                    "agent_id": "qa01",
                    "role": "qa",
                    "signal": "approved",
                    "message": "Looks good",
                    "workflow_id": wf_id,
                },
            ]
            (wf_dir / "events.log").write_text(
                "\n".join(json.dumps(e) for e in events)
            )

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].signals) == 2
            assert sessions[0].signals[0].signal == "done"
            assert sessions[0].signals[1].signal == "approved"
            assert sessions[0].signals[0].timestamp < sessions[0].signals[1].timestamp


# ---------------------------------------------------------------------------
# Integration: KPI Measurer Compatibility
# ---------------------------------------------------------------------------

class TestKPIMeasurerCompatibility:
    """Tests that changes support 100% vermas_task_visibility KPI."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        return VermasParser()

    def test_full_session_scores_100_percent(self, parser: VermasParser) -> None:
        """Full session has all 4 KPI sections present."""
        from session_insights.measurers.vermas_task_visibility import score_vermas_note

        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = _create_full_vermas_dir(Path(tmpdir))
            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])

            note_path = Path(tmpdir) / "test_note.md"
            note_path.write_text(note)

            scores = score_vermas_note(note_path)
            assert all(scores.values()), f"Some sections missing: {scores}"

    def test_fallback_session_scores_100_percent(self, parser: VermasParser) -> None:
        """Session using fallback task_description still has all 4 KPI sections."""
        from session_insights.measurers.vermas_task_visibility import score_vermas_note

        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            wf_id = "mission-fb-cycle-1-execute-fallback-task"
            sig_dir = vermas_dir / "state" / wf_id / "signals"
            sig_dir.mkdir(parents=True)
            _write_signal(sig_dir, _make_signal_yaml(
                "s1", "dev", "done", "Done", wf_id, "2024-01-15T10:00:00"
            ))

            # Learnings so ## Learnings section appears
            agents_dir = vermas_dir / "knowledge" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "agent-learnings.yaml").write_text(yaml.dump({
                "agents": {"general": {"learnings": ["A lesson"], "strengths": [], "weaknesses": [], "best_practices": []}}
            }))

            sessions = parser.parse_directory(vermas_dir)
            formatter = ObsidianFormatter(include_conversation=False)
            note = formatter.format_session(sessions[0])

            note_path = Path(tmpdir) / "test_fallback_note.md"
            note_path.write_text(note)

            scores = score_vermas_note(note_path)
            assert all(scores.values()), f"Some sections missing: {scores}"
