"""Tests for VerMAS workflow state parser."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from session_insights.parsers.models import (
    AgentLearning,
    AgentSignal,
    KnowledgeImprovement,
)
from session_insights.parsers.vermas import (
    MissionInfo,
    RecapFile,
    VermasParser,
    VermasSession,
    WorkflowExecution,
)


class TestAgentSignal:
    """Tests for AgentSignal model."""

    def test_signal_creation(self) -> None:
        """Test creating an AgentSignal object."""
        signal = AgentSignal(
            signal_id="abc123",
            agent_id="dev-001",
            role="dev",
            signal="done",
            message="Task completed",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            workflow_id="mission-123-cycle-1-execute-task",
        )
        assert signal.signal_id == "abc123"
        assert signal.agent_id == "dev-001"
        assert signal.role == "dev"
        assert signal.signal == "done"
        assert signal.message == "Task completed"

    def test_signal_with_metadata(self) -> None:
        """Test AgentSignal with metadata."""
        signal = AgentSignal(
            signal_id="abc123",
            agent_id="qa-001",
            role="qa",
            signal="approved",
            message="Looks good",
            timestamp=datetime.now(),
            workflow_id="test-workflow",
            metadata={"tests_passed": 10, "coverage": 85.0},
        )
        assert signal.metadata is not None
        assert signal.metadata["tests_passed"] == 10


class TestWorkflowExecution:
    """Tests for WorkflowExecution model."""

    def test_execution_duration(self) -> None:
        """Test duration calculation for workflow execution."""
        exec = WorkflowExecution(
            workflow_id="test-workflow",
            mission_id="123",
            cycle=1,
            task_name="implement-feature",
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            end_time=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert exec.duration_minutes == 30.0

    def test_execution_outcome_complete(self) -> None:
        """Test outcome determination for completed workflow."""
        signals = [
            AgentSignal(
                signal_id="1",
                agent_id="dev",
                role="dev",
                signal="done",
                message="",
                timestamp=datetime(2024, 1, 15, 10, 0),
                workflow_id="test",
            ),
            AgentSignal(
                signal_id="2",
                agent_id="qa",
                role="qa",
                signal="complete",
                message="",
                timestamp=datetime(2024, 1, 15, 10, 30),
                workflow_id="test",
            ),
        ]
        exec = WorkflowExecution(
            workflow_id="test",
            mission_id="123",
            cycle=1,
            task_name="task",
            signals=signals,
        )
        assert exec.outcome == "completed"

    def test_execution_outcome_approved(self) -> None:
        """Test outcome determination for approved workflow."""
        signals = [
            AgentSignal(
                signal_id="1",
                agent_id="dev",
                role="dev",
                signal="done",
                message="",
                timestamp=datetime(2024, 1, 15, 10, 0),
                workflow_id="test",
            ),
            AgentSignal(
                signal_id="2",
                agent_id="qa",
                role="qa",
                signal="approved",
                message="",
                timestamp=datetime(2024, 1, 15, 10, 30),
                workflow_id="test",
            ),
        ]
        exec = WorkflowExecution(
            workflow_id="test",
            mission_id="123",
            cycle=1,
            task_name="task",
            signals=signals,
        )
        assert exec.outcome == "approved"


class TestMissionInfo:
    """Tests for MissionInfo model."""

    def test_mission_info_creation(self) -> None:
        """Test creating a MissionInfo object."""
        info = MissionInfo(
            mission_id="abc123",
            status="in_progress",
            priority="high",
            title="Test Mission",
            description="A test mission",
        )
        assert info.mission_id == "abc123"
        assert info.status == "in_progress"
        assert info.priority == "high"
        assert info.title == "Test Mission"


class TestKnowledgeImprovement:
    """Tests for KnowledgeImprovement model."""

    def test_improvement_creation(self) -> None:
        """Test creating a KnowledgeImprovement object."""
        improvement = KnowledgeImprovement(
            id="improve-123",
            type="prompt",
            target="agent/dev",
            change="Added error handling",
            validated=True,
            impact="positive: 50% -> 75%",
        )
        assert improvement.id == "improve-123"
        assert improvement.type == "prompt"
        assert improvement.validated is True


class TestAgentLearning:
    """Tests for AgentLearning model."""

    def test_learning_creation(self) -> None:
        """Test creating an AgentLearning object."""
        learning = AgentLearning(
            agent="dev",
            learnings=["Use tests", "Check edge cases"],
            strengths=["Fast iteration"],
        )
        assert learning.agent == "dev"
        assert len(learning.learnings) == 2
        assert "Fast iteration" in learning.strengths


class TestVermasSession:
    """Tests for VermasSession model."""

    def test_session_source(self) -> None:
        """Test that VermasSession has correct source."""
        session = VermasSession(
            session_id="test-123",
            timestamp=datetime.now(),
        )
        assert session.source == "vermas"

    def test_session_note_name(self) -> None:
        """Test Obsidian note name generation."""
        ts = datetime(2024, 3, 15, 14, 30, 0)
        session = VermasSession(
            session_id="workflow-abc123-def456",
            timestamp=ts,
            task_name="implement-feature",
        )
        assert session.note_name == "vermas-2024-03-15-implement_feature-workflow"

    def test_session_duration_minutes(self) -> None:
        """Test session duration calculation."""
        session = VermasSession(
            session_id="test-123",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            end_time=datetime(2024, 1, 15, 10, 45, 0),
        )
        assert session.session_duration_minutes == 45.0

    def test_session_duration_minutes_none_when_missing(self) -> None:
        """Test session duration is None when times are missing."""
        session = VermasSession(
            session_id="test-123",
            timestamp=datetime.now(),
        )
        assert session.session_duration_minutes is None


class TestVermasParser:
    """Tests for VermasParser."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        """Create a parser instance."""
        return VermasParser()

    @pytest.fixture
    def temp_vermas_dir(self) -> Path:
        """Create a temporary .vermas directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            vermas_dir.mkdir()
            (vermas_dir / "state").mkdir()
            (vermas_dir / "tasks").mkdir()
            yield vermas_dir

    def test_parser_initialization(self, parser: VermasParser) -> None:
        """Test parser initialization."""
        assert parser.parse_errors == []

    def test_parse_empty_directory(self, parser: VermasParser) -> None:
        """Test parsing an empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = parser.parse_directory(Path(tmpdir))
            assert sessions == []

    def test_parse_vermas_directory(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test parsing a .vermas directory."""
        # Create a workflow directory with signals
        workflow_dir = temp_vermas_dir / "state" / "mission-abc-cycle-1-execute-test-task"
        workflow_dir.mkdir(parents=True)
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir()

        # Create a signal file
        signal_data = {
            "signal_id": "sig123",
            "agent_id": "dev001",
            "role": "dev",
            "signal": "done",
            "message": "Task completed",
            "workflow_id": "mission-abc-cycle-1-execute-test-task",
            "created_at": "2024-01-15T10:30:00",
        }
        (signals_dir / "sig123.yaml").write_text(yaml.dump(signal_data))

        sessions = parser.parse_directory(temp_vermas_dir)
        assert len(sessions) == 1
        assert sessions[0].mission_id == "abc"
        assert sessions[0].cycle == 1
        assert sessions[0].task_name == "test-task"

    def test_parse_signal_files(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test parsing multiple signal files."""
        workflow_dir = temp_vermas_dir / "state" / "mission-xyz-cycle-2-execute-feature"
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir(parents=True)

        # Create multiple signals
        signals = [
            {
                "signal_id": "s1",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "Done",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            },
            {
                "signal_id": "s2",
                "agent_id": "qa",
                "role": "qa",
                "signal": "approved",
                "message": "Approved",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:30:00",
            },
        ]
        for sig in signals:
            (signals_dir / f"{sig['signal_id']}.yaml").write_text(yaml.dump(sig))

        sessions = parser.parse_directory(temp_vermas_dir)
        assert len(sessions) == 1
        assert len(sessions[0].signals) == 2
        assert sessions[0].outcome == "approved"

    def test_parse_events_log(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test parsing events.log file."""
        workflow_dir = temp_vermas_dir / "state" / "mission-log-cycle-1-execute-task"
        workflow_dir.mkdir(parents=True)

        # Create events.log with signal entries
        events = [
            {
                "type": "signal",
                "timestamp": "2024-01-15T10:00:00",
                "signal_id": "e1",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "Complete",
                "workflow_id": "test",
            },
        ]
        (workflow_dir / "events.log").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        sessions = parser.parse_directory(temp_vermas_dir)
        assert len(sessions) == 1
        assert len(sessions[0].signals) == 1
        assert sessions[0].signals[0].signal == "done"

    def test_discover_missions(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test mission discovery."""
        # Create multiple workflows with different missions
        for mission_id in ["abc", "def", "ghi"]:
            workflow_dir = (
                temp_vermas_dir / "state" / f"mission-{mission_id}-cycle-1-execute-task"
            )
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": f"mission-{mission_id}-cycle-1-execute-task",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

        missions = parser.discover_missions(temp_vermas_dir)
        assert len(missions) == 3
        assert "abc" in missions
        assert "def" in missions
        assert "ghi" in missions

    def test_multi_cycle_tracking(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test tracking multiple cycles of the same mission."""
        for cycle in [1, 2, 3]:
            workflow_dir = (
                temp_vermas_dir / "state" / f"mission-xyz-cycle-{cycle}-execute-task"
            )
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": f"sig{cycle}",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": f"Cycle {cycle}",
                "workflow_id": f"mission-xyz-cycle-{cycle}-execute-task",
                "created_at": f"2024-01-15T1{cycle}:00:00",
            }
            (signals_dir / f"sig{cycle}.yaml").write_text(yaml.dump(signal_data))

        sessions = parser.parse_directory(temp_vermas_dir)
        assert len(sessions) == 3
        cycles = sorted([s.cycle for s in sessions])
        assert cycles == [1, 2, 3]

    def test_parse_workflow_id_components(self, parser: VermasParser) -> None:
        """Test parsing workflow ID into components."""
        mission_id, cycle, task_name = parser._parse_workflow_id(
            "mission-abc123-cycle-5-execute-implement-feature"
        )
        assert mission_id == "abc123"
        assert cycle == 5
        assert task_name == "implement-feature"

    def test_handle_malformed_yaml(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test graceful handling of malformed YAML signal files."""
        workflow_dir = temp_vermas_dir / "state" / "mission-bad-cycle-1-execute-task"
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir(parents=True)

        # Create a valid signal
        valid_signal = {
            "signal_id": "valid",
            "agent_id": "dev",
            "role": "dev",
            "signal": "done",
            "message": "Valid",
            "workflow_id": "test",
            "created_at": "2024-01-15T10:00:00",
        }
        (signals_dir / "valid.yaml").write_text(yaml.dump(valid_signal))

        # Create a malformed signal file
        (signals_dir / "bad.yaml").write_text("{{{{invalid yaml content")

        sessions = parser.parse_directory(temp_vermas_dir)
        # Should still parse the valid signal
        assert len(sessions) == 1
        assert len(sessions[0].signals) >= 1
        assert len(parser.parse_errors) > 0

    def test_handle_missing_timestamp(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test handling signal files with missing timestamps."""
        workflow_dir = temp_vermas_dir / "state" / "mission-notime-cycle-1-execute-task"
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir(parents=True)

        # Signal without timestamp
        signal_data = {
            "signal_id": "sig",
            "agent_id": "dev",
            "role": "dev",
            "signal": "done",
            "message": "No timestamp",
            "workflow_id": "test",
            # missing created_at
        }
        (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

        sessions = parser.parse_directory(temp_vermas_dir)
        # Should not create session for signal without timestamp
        assert len(sessions) == 0

    def test_skip_meeting_directories(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test that meeting directories (mtg-*) are skipped."""
        # Create a meeting directory
        mtg_dir = temp_vermas_dir / "state" / "mtg-abc123"
        signals_dir = mtg_dir / "signals"
        signals_dir.mkdir(parents=True)
        signal_data = {
            "signal_id": "sig",
            "agent_id": "dev",
            "role": "dev",
            "signal": "done",
            "message": "",
            "workflow_id": "mtg-abc123",
            "created_at": "2024-01-15T10:00:00",
        }
        (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

        sessions = parser.parse_directory(temp_vermas_dir)
        assert len(sessions) == 0

    def test_get_workflow_executions(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test getting detailed workflow execution data."""
        workflow_dir = temp_vermas_dir / "state" / "mission-exec-cycle-1-execute-task"
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir(parents=True)

        signals = [
            {
                "signal_id": "s1",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            },
            {
                "signal_id": "s2",
                "agent_id": "qa",
                "role": "qa",
                "signal": "complete",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:30:00",
            },
        ]
        for sig in signals:
            (signals_dir / f"{sig['signal_id']}.yaml").write_text(yaml.dump(sig))

        executions = parser.get_workflow_executions(temp_vermas_dir)
        assert len(executions) == 1
        exec = executions[0]
        assert exec.mission_id == "exec"
        assert exec.cycle == 1
        assert exec.task_name == "task"
        assert len(exec.signals) == 2
        assert exec.outcome == "completed"
        assert exec.duration_minutes == 30.0

    def test_outcome_determination(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test various outcome determinations."""
        # Test needs_revision outcome
        workflow_dir = temp_vermas_dir / "state" / "mission-rev-cycle-1-execute-task"
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir(parents=True)

        signal_data = {
            "signal_id": "sig",
            "agent_id": "qa",
            "role": "qa",
            "signal": "needs_revision",
            "message": "Please fix",
            "workflow_id": "test",
            "created_at": "2024-01-15T10:00:00",
        }
        (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

        sessions = parser.parse_directory(temp_vermas_dir)
        assert len(sessions) == 1
        assert sessions[0].outcome == "needs_revision"

    def test_parse_from_parent_directory(self, parser: VermasParser) -> None:
        """Test parsing when given parent directory containing .vermas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            vermas_dir = parent / ".vermas"
            vermas_dir.mkdir()
            state_dir = vermas_dir / "state"
            state_dir.mkdir()

            workflow_dir = state_dir / "mission-parent-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)

            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            # Parse from parent directory
            sessions = parser.parse_directory(parent)
            assert len(sessions) == 1

    def test_parse_errors_cleared_on_new_parse(
        self, parser: VermasParser, temp_vermas_dir: Path
    ) -> None:
        """Test that parse errors are cleared on each parse call."""
        # First parse with error
        workflow_dir = temp_vermas_dir / "state" / "mission-err-cycle-1-execute-task"
        signals_dir = workflow_dir / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "bad.yaml").write_text("{{invalid")

        parser.parse_directory(temp_vermas_dir)
        assert len(parser.parse_errors) > 0

        # Clean up and create a good parse
        (signals_dir / "bad.yaml").unlink()
        signal_data = {
            "signal_id": "sig",
            "agent_id": "dev",
            "role": "dev",
            "signal": "done",
            "message": "",
            "workflow_id": "test",
            "created_at": "2024-01-15T10:00:00",
        }
        (signals_dir / "good.yaml").write_text(yaml.dump(signal_data))

        parser.parse_directory(temp_vermas_dir)
        assert len(parser.parse_errors) == 0


class TestVermasParserEdgeCases:
    """Edge case tests for parser robustness."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        """Create a parser instance."""
        return VermasParser()

    def test_empty_signals_directory(self, parser: VermasParser) -> None:
        """Test handling workflow with empty signals directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            workflow_dir = vermas_dir / "state" / "mission-empty-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 0

    def test_workflow_with_blocked_signal(self, parser: VermasParser) -> None:
        """Test workflow that ended with blocked signal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            workflow_dir = vermas_dir / "state" / "mission-blk-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)

            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "blocked",
                "message": "Cannot proceed",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].outcome == "blocked"

    def test_filter_by_mission_id(self, parser: VermasParser) -> None:
        """Test filtering workflow executions by mission ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            state_dir = vermas_dir / "state"
            state_dir.mkdir(parents=True)

            # Create workflows for two different missions
            for mission_id in ["target", "other"]:
                workflow_dir = state_dir / f"mission-{mission_id}-cycle-1-execute-task"
                signals_dir = workflow_dir / "signals"
                signals_dir.mkdir(parents=True)
                signal_data = {
                    "signal_id": "sig",
                    "agent_id": "dev",
                    "role": "dev",
                    "signal": "done",
                    "message": "",
                    "workflow_id": f"mission-{mission_id}-cycle-1-execute-task",
                    "created_at": "2024-01-15T10:00:00",
                }
                (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            # Filter by mission ID
            executions = parser.get_workflow_executions(vermas_dir, mission_id="target")
            assert len(executions) == 1
            assert executions[0].mission_id == "target"

    def test_complex_task_name_parsing(self, parser: VermasParser) -> None:
        """Test parsing task names with multiple hyphens."""
        mission_id, cycle, task_name = parser._parse_workflow_id(
            "mission-abc-cycle-2-execute-implement-multi-part-feature-name"
        )
        assert mission_id == "abc"
        assert cycle == 2
        assert task_name == "implement-multi-part-feature-name"

    def test_timestamp_with_z_suffix(self, parser: VermasParser) -> None:
        """Test parsing timestamps with Z suffix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            workflow_dir = vermas_dir / "state" / "mission-tz-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)

            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00Z",  # Z suffix
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].timestamp is not None


class TestMissionFileParsing:
    """Tests for mission file (_epic.md) parsing."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        """Create a parser instance."""
        return VermasParser()

    def test_parse_mission_info(self, parser: VermasParser) -> None:
        """Test parsing mission info from _epic.md file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create mission task directory with _epic.md
            mission_dir = vermas_dir / "tasks" / "mission-mission-abc123"
            mission_dir.mkdir(parents=True)
            epic_content = """---
status: in_progress
priority: high
---

# Mission abc123

This is a test mission for feature development.
"""
            (mission_dir / "_epic.md").write_text(epic_content)

            # Create workflow with signal
            workflow_dir = vermas_dir / "state" / "mission-abc123-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].mission_info is not None
            assert sessions[0].mission_info.status == "in_progress"
            assert sessions[0].mission_info.priority == "high"
            assert sessions[0].mission_info.title == "Mission abc123"

    def test_parse_mission_info_no_frontmatter(self, parser: VermasParser) -> None:
        """Test parsing mission info without YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            mission_dir = vermas_dir / "tasks" / "mission-mission-xyz"
            mission_dir.mkdir(parents=True)
            epic_content = "# Simple Mission\n\nNo frontmatter here."
            (mission_dir / "_epic.md").write_text(epic_content)

            workflow_dir = vermas_dir / "state" / "mission-xyz-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].mission_info is not None
            assert sessions[0].mission_info.title == "Simple Mission"


class TestKnowledgeParsing:
    """Tests for knowledge/improvements and agent learnings parsing."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        """Create a parser instance."""
        return VermasParser()

    def test_parse_improvements(self, parser: VermasParser) -> None:
        """Test parsing knowledge improvement files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create improvement file
            imp_dir = vermas_dir / "knowledge" / "improvements"
            imp_dir.mkdir(parents=True)
            imp_data = {
                "id": "adapt-mission-test123-c1-dev",
                "date": "2024-01-15T10:00:00",
                "type": "prompt",
                "target": "agent/dev",
                "change": "Added error handling instructions",
                "before_metrics": {"success_rate": 0.5},
                "after_metrics": {"success_rate": 0.8},
                "validated": True,
                "impact": "positive: 50% -> 80%",
            }
            (imp_dir / "adapt-mission-test123-c1-dev.yaml").write_text(yaml.dump(imp_data))

            # Create workflow
            workflow_dir = vermas_dir / "state" / "mission-test123-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].improvements) == 1
            assert sessions[0].improvements[0].validated is True
            assert sessions[0].improvements[0].target == "agent/dev"

    def test_parse_agent_learnings(self, parser: VermasParser) -> None:
        """Test parsing agent learnings from knowledge files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create agent learnings file
            agents_dir = vermas_dir / "knowledge" / "agents"
            agents_dir.mkdir(parents=True)
            learnings_data = {
                "agents": {
                    "general": {
                        "learnings": [
                            "Dev demonstrated effective debugging",
                            "QA caught subtle issues",
                        ],
                        "strengths": ["Quick iteration"],
                        "weaknesses": [],
                        "best_practices": ["Write tests first"],
                    }
                }
            }
            (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings_data))

            # Create workflow
            workflow_dir = vermas_dir / "state" / "mission-learn-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].learnings) == 1
            assert sessions[0].learnings[0].agent == "general"
            assert len(sessions[0].learnings[0].learnings) == 2

    def test_parse_empty_learnings(self, parser: VermasParser) -> None:
        """Test handling of empty agent learnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create agent learnings file with null values
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

            # Create workflow
            workflow_dir = vermas_dir / "state" / "mission-null-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            # Should handle None values gracefully
            assert len(sessions[0].learnings) == 1
            assert sessions[0].learnings[0].learnings == []


class TestRecapFile:
    """Tests for RecapFile model."""

    def test_recap_file_creation(self) -> None:
        """Test creating a RecapFile object."""
        recap = RecapFile(
            file_path="/path/to/recap.md",
            title="Workflow Recap",
            status="done",
            content="This is the recap content.",
        )
        assert recap.file_path == "/path/to/recap.md"
        assert recap.title == "Workflow Recap"
        assert recap.status == "done"


class TestRecapParsing:
    """Tests for recap file parsing."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        """Create a parser instance."""
        return VermasParser()

    def test_parse_recap_files(self, parser: VermasParser) -> None:
        """Test parsing recap files from tasks directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create recap file in tasks directory
            recap_dir = vermas_dir / "tasks" / "observability" / "workflow-recap"
            recap_dir.mkdir(parents=True)
            recap_content = """---
status: done
priority: medium
---

# Generate workflow recap after completion

This task generates a recap of the workflow execution.
"""
            (recap_dir / "recap-generator.md").write_text(recap_content)

            # Create workflow with signal
            workflow_dir = vermas_dir / "state" / "mission-recap-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].recaps) == 1
            assert sessions[0].recaps[0].title == "Generate workflow recap after completion"
            assert sessions[0].recaps[0].status == "done"

    def test_parse_multiple_recap_files(self, parser: VermasParser) -> None:
        """Test parsing multiple recap files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create multiple recap files
            recap_dir = vermas_dir / "tasks" / "recaps"
            recap_dir.mkdir(parents=True)
            for i, name in enumerate(["recap-summary.md", "mission-recap.md"]):
                content = f"""---
status: done
---

# Recap {i + 1}

Content for recap {i + 1}.
"""
                (recap_dir / name).write_text(content)

            # Create workflow
            workflow_dir = vermas_dir / "state" / "mission-multi-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].recaps) == 2

    def test_parse_recap_without_frontmatter(self, parser: VermasParser) -> None:
        """Test parsing recap file without YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            recap_dir = vermas_dir / "tasks" / "docs"
            recap_dir.mkdir(parents=True)
            content = "# Simple Recap\n\nNo frontmatter here."
            (recap_dir / "simple-recap.md").write_text(content)

            # Create workflow
            workflow_dir = vermas_dir / "state" / "mission-simple-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].recaps) == 1
            assert sessions[0].recaps[0].title == "Simple Recap"
            assert sessions[0].recaps[0].status == "unknown"

    def test_no_recap_files(self, parser: VermasParser) -> None:
        """Test handling when no recap files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"

            # Create tasks directory without recap files
            tasks_dir = vermas_dir / "tasks" / "other"
            tasks_dir.mkdir(parents=True)
            (tasks_dir / "regular-task.md").write_text("# Regular Task\n\nNot a recap.")

            # Create workflow
            workflow_dir = vermas_dir / "state" / "mission-norecap-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)
            signal_data = {
                "signal_id": "sig",
                "agent_id": "dev",
                "role": "dev",
                "signal": "done",
                "message": "",
                "workflow_id": "test",
                "created_at": "2024-01-15T10:00:00",
            }
            (signals_dir / "sig.yaml").write_text(yaml.dump(signal_data))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert len(sessions[0].recaps) == 0


class TestDurationTracking:
    """Tests for session duration tracking."""

    @pytest.fixture
    def parser(self) -> VermasParser:
        """Create a parser instance."""
        return VermasParser()

    def test_session_has_start_end_times(self, parser: VermasParser) -> None:
        """Test that session has start and end times from signals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            workflow_dir = vermas_dir / "state" / "mission-dur-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)

            signals = [
                {
                    "signal_id": "s1",
                    "agent_id": "dev",
                    "role": "dev",
                    "signal": "done",
                    "message": "",
                    "workflow_id": "test",
                    "created_at": "2024-01-15T10:00:00",
                },
                {
                    "signal_id": "s2",
                    "agent_id": "qa",
                    "role": "qa",
                    "signal": "complete",
                    "message": "",
                    "workflow_id": "test",
                    "created_at": "2024-01-15T10:30:00",
                },
            ]
            for sig in signals:
                (signals_dir / f"{sig['signal_id']}.yaml").write_text(yaml.dump(sig))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert sessions[0].start_time is not None
            assert sessions[0].end_time is not None
            assert sessions[0].session_duration_minutes == 30.0

    def test_summary_includes_duration(self, parser: VermasParser) -> None:
        """Test that summary includes duration when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vermas_dir = Path(tmpdir) / ".vermas"
            workflow_dir = vermas_dir / "state" / "mission-sum-cycle-1-execute-task"
            signals_dir = workflow_dir / "signals"
            signals_dir.mkdir(parents=True)

            signals = [
                {
                    "signal_id": "s1",
                    "agent_id": "dev",
                    "role": "dev",
                    "signal": "done",
                    "message": "",
                    "workflow_id": "test",
                    "created_at": "2024-01-15T10:00:00",
                },
                {
                    "signal_id": "s2",
                    "agent_id": "qa",
                    "role": "qa",
                    "signal": "complete",
                    "message": "",
                    "workflow_id": "test",
                    "created_at": "2024-01-15T10:15:00",
                },
            ]
            for sig in signals:
                (signals_dir / f"{sig['signal_id']}.yaml").write_text(yaml.dump(sig))

            sessions = parser.parse_directory(vermas_dir)
            assert len(sessions) == 1
            assert "Duration: 15.0m" in sessions[0].summary
