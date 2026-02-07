"""VerMAS workflow state parser for .vermas/ directory.

Parses VerMAS (Verification Multi-Agent System) workflow state including:
- Mission files and task definitions
- Cycle directories with agent executions
- Signal files (done/approved/blocked/needs_revision/complete)
- Events logs tracking workflow progression
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .models import (
    AgentLearning,
    AgentSignal,
    BaseSession,
    CycleInfo,
    KnowledgeImprovement,
)

logger = logging.getLogger(__name__)


class WorkflowExecution(BaseModel):
    """Represents a single workflow execution (cycle)."""

    workflow_id: str
    mission_id: str
    cycle: int
    task_name: str
    signals: list[AgentSignal] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_minutes(self) -> float | None:
        """Calculate execution duration in minutes."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() / 60
        return None

    @property
    def outcome(self) -> str:
        """Determine workflow outcome from signals."""
        for signal in reversed(self.signals):
            if signal.signal == "complete":
                return "completed"
            elif signal.signal == "approved":
                return "approved"
            elif signal.signal == "blocked":
                return "blocked"
        if any(s.signal == "done" for s in self.signals):
            return "done"
        return "in_progress"


class MissionInfo(BaseModel):
    """Information about a VerMAS mission parsed from _epic.md files."""

    mission_id: str
    status: str = "unknown"
    priority: str = "medium"
    title: str = ""
    description: str = ""


class RecapFile(BaseModel):
    """Represents a workflow recap file."""

    file_path: str
    title: str = ""
    status: str = "unknown"
    content: str = ""


class VermasSession(BaseSession):
    """Represents a parsed VerMAS workflow session.

    Extends BaseSession with VerMAS-specific fields for tracking
    multi-agent workflow executions. Inherits signals, learnings,
    improvements, task_description, and cycle_info from BaseSession.
    """

    source: str = "vermas"
    mission_id: str | None = None
    task_name: str | None = None
    cycle: int | None = None
    workflow_id: str | None = None
    outcome: str = "unknown"  # completed, approved, blocked, done, in_progress
    quality_rating: str | None = None
    mission_info: MissionInfo | None = None
    recaps: list[RecapFile] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Auto-derive cycle_info from VerMAS-specific fields."""
        super().model_post_init(__context)
        if self.cycle_info is None and (self.mission_id or self.cycle is not None):
            self.cycle_info = CycleInfo(
                mission_id=self.mission_id,
                cycle=self.cycle,
                workflow_id=self.workflow_id,
                task_name=self.task_name,
                outcome=self.outcome,
                quality_rating=self.quality_rating,
            )

    @property
    def session_duration_minutes(self) -> float | None:
        """Calculate session duration in minutes from start/end times."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() / 60
        return None

    @property
    def note_name(self) -> str:
        """Generate Obsidian-compatible note name."""
        date_str = self.timestamp.strftime("%Y-%m-%d")
        task_slug = (self.task_name or "unknown").replace("-", "_")[:20]
        return f"vermas-{date_str}-{task_slug}-{self.session_id[:8]}"


class VermasParser:
    """Parser for VerMAS workflow state stored in .vermas/ directory.

    Handles the directory structure:
    - .vermas/state/mission-XXX-cycle-N-execute-task-name/
      - signals/*.yaml - Agent signals with timestamps
      - events.log - JSONL event log
    - .vermas/tasks/mission-XXX/*/task-name.md - Task descriptions
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self._parse_errors: list[str] = []

    @property
    def parse_errors(self) -> list[str]:
        """Return any errors encountered during parsing."""
        return self._parse_errors.copy()

    def parse_directory(self, path: Path) -> list[VermasSession]:
        """Parse all VerMAS workflow sessions from a directory.

        Args:
            path: Path to .vermas directory or parent containing .vermas

        Returns:
            List of parsed VermasSession objects
        """
        self._parse_errors = []
        sessions: list[VermasSession] = []

        # Locate .vermas directory
        vermas_dir = self._find_vermas_directory(path)
        if vermas_dir is None:
            return sessions

        # Parse workflow executions from state directory
        state_dir = vermas_dir / "state"
        if state_dir.exists():
            sessions.extend(self._parse_state_directory(state_dir, vermas_dir))

        return sessions

    def _find_vermas_directory(self, path: Path) -> Path | None:
        """Locate the .vermas directory from given path."""
        if path.name == ".vermas":
            return path
        elif (path / ".vermas").exists():
            return path / ".vermas"
        return None

    def _parse_state_directory(
        self, state_dir: Path, vermas_dir: Path
    ) -> list[VermasSession]:
        """Parse all workflow executions from the state directory."""
        sessions: list[VermasSession] = []

        for workflow_dir in state_dir.iterdir():
            if not workflow_dir.is_dir():
                continue

            # Skip meeting directories (mtg-*)
            if workflow_dir.name.startswith("mtg-"):
                continue

            try:
                session = self._parse_workflow_directory(workflow_dir, vermas_dir)
                if session is not None:
                    sessions.append(session)
            except Exception as e:
                error_msg = f"Error parsing {workflow_dir}: {e}"
                logger.warning(error_msg)
                self._parse_errors.append(error_msg)

        return sessions

    def _parse_workflow_directory(
        self, workflow_dir: Path, vermas_dir: Path
    ) -> VermasSession | None:
        """Parse a single workflow execution directory.

        Directory names follow pattern: mission-XXX-cycle-N-execute-task-name
        """
        workflow_id = workflow_dir.name
        mission_id, cycle, task_name = self._parse_workflow_id(workflow_id)

        # Parse signals
        signals = self._parse_signals_directory(workflow_dir / "signals")
        if not signals:
            # Also try parsing events.log if no signals
            signals = self._parse_events_log(workflow_dir / "events.log")

        if not signals:
            return None

        # Determine timestamps
        timestamps = [s.timestamp for s in signals]
        start_time = min(timestamps) if timestamps else None
        end_time = max(timestamps) if timestamps else None

        # Determine outcome
        outcome = self._determine_outcome(signals)

        # Get mission info (before task_description so we can use it as fallback)
        mission_info = self._get_mission_info(vermas_dir, mission_id)

        # Get task description with fallback chain
        task_description = self._get_task_description(
            vermas_dir, mission_id, task_name
        )
        if not task_description and mission_info and mission_info.description:
            task_description = mission_info.description
        if not task_description and task_name:
            task_description = task_name.replace("-", " ").capitalize()

        # Get improvements related to this mission
        improvements = self._get_mission_improvements(vermas_dir, mission_id)

        # Get agent learnings
        agent_learnings = self._get_agent_learnings(vermas_dir)

        # Get recap files
        recaps = self._get_recaps(vermas_dir, mission_id, task_name)

        # Determine quality rating from outcome
        quality_rating = self._determine_quality_rating(outcome, signals)

        return VermasSession(
            session_id=workflow_id,
            timestamp=start_time or datetime.now(),
            mission_id=mission_id,
            task_name=task_name,
            cycle=cycle,
            workflow_id=workflow_id,
            signals=signals,
            outcome=outcome,
            task_description=task_description,
            start_time=start_time,
            end_time=end_time,
            mission_info=mission_info,
            improvements=improvements,
            learnings=agent_learnings,
            recaps=recaps,
            summary=self._generate_summary(signals, outcome, task_name, start_time, end_time),
            quality_rating=quality_rating,
        )

    def _parse_workflow_id(
        self, workflow_id: str
    ) -> tuple[str | None, int | None, str | None]:
        """Parse workflow ID into components.

        Format: mission-XXX-cycle-N-execute-task-name
        Returns: (mission_id, cycle, task_name)
        """
        parts = workflow_id.split("-")

        mission_id = None
        cycle = None
        task_name = None

        # Find mission ID (after "mission-")
        for i, part in enumerate(parts):
            if part == "mission" and i + 1 < len(parts):
                mission_id = parts[i + 1]
                break

        # Find cycle number (after "cycle-")
        for i, part in enumerate(parts):
            if part == "cycle" and i + 1 < len(parts):
                try:
                    cycle = int(parts[i + 1])
                except ValueError:
                    pass
                break

        # Find task name (after "execute-")
        for i, part in enumerate(parts):
            if part == "execute" and i + 1 < len(parts):
                task_name = "-".join(parts[i + 1 :])
                break

        return mission_id, cycle, task_name

    def _parse_signals_directory(self, signals_dir: Path) -> list[AgentSignal]:
        """Parse all signal files from a signals directory."""
        signals: list[AgentSignal] = []

        if not signals_dir.exists():
            return signals

        for signal_file in signals_dir.glob("*.yaml"):
            try:
                signal = self._parse_signal_file(signal_file)
                if signal:
                    signals.append(signal)
            except Exception as e:
                error_msg = f"Error parsing signal {signal_file}: {e}"
                logger.debug(error_msg)
                self._parse_errors.append(error_msg)

        # Sort by timestamp
        signals.sort(key=lambda s: s.timestamp)
        return signals

    def _parse_signal_file(self, file_path: Path) -> AgentSignal | None:
        """Parse a single YAML signal file."""
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        timestamp = self._parse_timestamp(data.get("created_at"))
        if timestamp is None:
            return None

        return AgentSignal(
            signal_id=data.get("signal_id", file_path.stem),
            agent_id=data.get("agent_id", "unknown"),
            role=data.get("role", "unknown"),
            signal=data.get("signal", "unknown"),
            message=data.get("message", ""),
            timestamp=timestamp,
            workflow_id=data.get("workflow_id", ""),
            metadata=data.get("metadata"),
        )

    def _parse_events_log(self, events_file: Path) -> list[AgentSignal]:
        """Parse events.log JSONL file for signals."""
        signals: list[AgentSignal] = []

        if not events_file.exists():
            return signals

        with open(events_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    if entry.get("type") == "signal":
                        signal = self._parse_signal_entry(entry)
                        if signal:
                            signals.append(signal)
                except json.JSONDecodeError as e:
                    error_msg = f"JSON error in {events_file}: {e}"
                    logger.debug(error_msg)
                    self._parse_errors.append(error_msg)

        # Sort by timestamp
        signals.sort(key=lambda s: s.timestamp)
        return signals

    def _parse_signal_entry(self, entry: dict[str, Any]) -> AgentSignal | None:
        """Parse a signal entry from events.log."""
        timestamp = self._parse_timestamp(entry.get("timestamp"))
        if timestamp is None:
            return None

        return AgentSignal(
            signal_id=entry.get("signal_id", "unknown"),
            agent_id=entry.get("agent_id", "unknown"),
            role=entry.get("role", "unknown"),
            signal=entry.get("signal", "unknown"),
            message=entry.get("message", ""),
            timestamp=timestamp,
            workflow_id=entry.get("workflow_id", ""),
            metadata=entry.get("metadata"),
        )

    def _parse_timestamp(self, ts_str: str | None) -> datetime | None:
        """Parse an ISO format timestamp string."""
        if ts_str is None:
            return None

        try:
            # Handle ISO format with Z suffix
            if isinstance(ts_str, str):
                if ts_str.endswith("Z"):
                    ts_str = ts_str[:-1] + "+00:00"
                return datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            return None

        return None

    def _determine_outcome(self, signals: list[AgentSignal]) -> str:
        """Determine workflow outcome from signals."""
        if not signals:
            return "unknown"

        for signal in reversed(signals):
            if signal.signal == "complete":
                return "completed"
            elif signal.signal == "approved":
                return "approved"
            elif signal.signal == "blocked":
                return "blocked"

        if any(s.signal == "done" for s in signals):
            return "done"
        if any(s.signal == "needs_revision" for s in signals):
            return "needs_revision"

        return "in_progress"

    def _determine_quality_rating(
        self, outcome: str, signals: list[AgentSignal]
    ) -> str:
        """Determine quality rating from outcome and signals.

        Ratings: excellent, good, fair, poor, unknown.
        """
        if outcome in ("completed", "approved"):
            has_needs_revision = any(s.signal == "needs_revision" for s in signals)
            return "good" if has_needs_revision else "excellent"
        elif outcome == "done":
            return "good"
        elif outcome == "needs_revision":
            return "fair"
        elif outcome == "blocked":
            return "poor"
        return "unknown"

    def _get_task_description(
        self, vermas_dir: Path, mission_id: str | None, task_name: str | None
    ) -> str:
        """Get task description from task files."""
        if not mission_id or not task_name:
            return ""

        tasks_dir = vermas_dir / "tasks"
        if not tasks_dir.exists():
            return ""

        # Search for task file: .vermas/tasks/mission-XXX/*/task-name.md
        for mission_dir in tasks_dir.iterdir():
            if not mission_dir.is_dir():
                continue
            # Check if mission ID matches (in dir name)
            if mission_id not in mission_dir.name:
                continue

            for feature_dir in mission_dir.iterdir():
                if not feature_dir.is_dir():
                    continue

                task_file = feature_dir / f"{task_name}.md"
                if task_file.exists():
                    try:
                        return self._parse_task_file(task_file)
                    except Exception as e:
                        logger.debug(f"Error reading task file {task_file}: {e}")

        return ""

    def _parse_task_file(self, file_path: Path) -> str:
        """Parse a task markdown file and extract description."""
        content = file_path.read_text(encoding="utf-8")

        # Skip YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        # Extract first paragraph after heading
        lines = content.split("\n")
        description_lines = []
        in_description = False

        for line in lines:
            if line.startswith("#"):
                in_description = True
                continue
            if in_description:
                if line.strip() == "":
                    if description_lines:
                        break
                else:
                    description_lines.append(line.strip())

        return " ".join(description_lines)

    def _generate_summary(
        self,
        signals: list[AgentSignal],
        outcome: str,
        task_name: str | None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """Generate a summary of the workflow execution."""
        if not signals:
            return f"Task: {task_name or 'unknown'} - No signals recorded"

        roles_involved = list(set(s.role for s in signals))

        summary_parts = [f"Task: {task_name or 'unknown'}"]
        summary_parts.append(f"Outcome: {outcome}")
        summary_parts.append(f"Roles: {', '.join(roles_involved)}")
        summary_parts.append(f"Signals: {len(signals)}")

        # Add duration if available
        if start_time and end_time:
            duration_mins = (end_time - start_time).total_seconds() / 60
            summary_parts.append(f"Duration: {duration_mins:.1f}m")

        return " | ".join(summary_parts)

    def _get_mission_info(
        self, vermas_dir: Path, mission_id: str | None
    ) -> MissionInfo | None:
        """Parse mission info from _epic.md file."""
        if not mission_id:
            return None

        tasks_dir = vermas_dir / "tasks"
        if not tasks_dir.exists():
            return None

        # Search for mission directory: .vermas/tasks/mission-XXX/_epic.md
        for mission_dir in tasks_dir.iterdir():
            if not mission_dir.is_dir():
                continue
            if mission_id not in mission_dir.name:
                continue

            epic_file = mission_dir / "_epic.md"
            if epic_file.exists():
                try:
                    return self._parse_epic_file(epic_file, mission_id)
                except Exception as e:
                    logger.debug(f"Error parsing epic file {epic_file}: {e}")

        return None

    def _parse_epic_file(self, file_path: Path, mission_id: str) -> MissionInfo:
        """Parse a mission _epic.md file."""
        content = file_path.read_text(encoding="utf-8")

        status = "unknown"
        priority = "medium"
        title = ""
        description = ""

        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    if frontmatter:
                        status = frontmatter.get("status", "unknown")
                        priority = frontmatter.get("priority", "medium")
                except yaml.YAMLError:
                    pass
                content = parts[2].strip()

        # Extract title and description from markdown
        lines = content.split("\n")
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
            elif title and line.strip() and not line.startswith("#"):
                description = line.strip()
                break

        return MissionInfo(
            mission_id=mission_id,
            status=status,
            priority=priority,
            title=title,
            description=description,
        )

    def _get_mission_improvements(
        self, vermas_dir: Path, mission_id: str | None
    ) -> list[KnowledgeImprovement]:
        """Parse improvement records for a mission from knowledge files."""
        improvements: list[KnowledgeImprovement] = []

        if not mission_id:
            return improvements

        knowledge_dir = vermas_dir / "knowledge" / "improvements"
        if not knowledge_dir.exists():
            return improvements

        # Find improvement files matching this mission
        for imp_file in knowledge_dir.glob(f"*{mission_id}*.yaml"):
            try:
                improvement = self._parse_improvement_file(imp_file)
                if improvement:
                    improvements.append(improvement)
            except Exception as e:
                logger.debug(f"Error parsing improvement file {imp_file}: {e}")
                self._parse_errors.append(f"Error parsing {imp_file}: {e}")

        return improvements

    def _parse_improvement_file(self, file_path: Path) -> KnowledgeImprovement | None:
        """Parse a knowledge improvement YAML file."""
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        date = None
        date_str = data.get("date")
        if date_str:
            date = self._parse_timestamp(str(date_str))

        return KnowledgeImprovement(
            id=data.get("id", file_path.stem),
            date=date,
            type=data.get("type", ""),
            target=data.get("target", ""),
            change=data.get("change", ""),
            before_metrics=data.get("before_metrics", {}),
            after_metrics=data.get("after_metrics", {}),
            validated=data.get("validated", False),
            impact=data.get("impact", ""),
        )

    def _get_agent_learnings(self, vermas_dir: Path) -> list[AgentLearning]:
        """Parse agent learnings from knowledge files."""
        learnings: list[AgentLearning] = []

        learnings_file = vermas_dir / "knowledge" / "agents" / "agent-learnings.yaml"
        if not learnings_file.exists():
            return learnings

        try:
            with open(learnings_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data and "agents" in data:
                for agent_name, agent_data in data["agents"].items():
                    if agent_data:
                        learning = AgentLearning(
                            agent=agent_name,
                            learnings=agent_data.get("learnings", []) or [],
                            strengths=agent_data.get("strengths", []) or [],
                            weaknesses=agent_data.get("weaknesses", []) or [],
                            best_practices=agent_data.get("best_practices", []) or [],
                        )
                        learnings.append(learning)
        except Exception as e:
            logger.debug(f"Error parsing agent learnings: {e}")
            self._parse_errors.append(f"Error parsing agent learnings: {e}")

        return learnings

    def _get_recaps(
        self,
        vermas_dir: Path,
        mission_id: str | None,
        task_name: str | None,
    ) -> list[RecapFile]:
        """Parse recap files from .vermas directory.

        Searches for recap files in:
        - .vermas/tasks/**/recap*.md
        - .vermas/tasks/**/*recap*.md
        - Any markdown file containing 'recap' in the name
        """
        recaps: list[RecapFile] = []

        tasks_dir = vermas_dir / "tasks"
        if not tasks_dir.exists():
            return recaps

        # Search for recap files recursively
        for recap_file in tasks_dir.rglob("*recap*.md"):
            try:
                recap = self._parse_recap_file(recap_file)
                if recap:
                    recaps.append(recap)
            except Exception as e:
                logger.debug(f"Error parsing recap file {recap_file}: {e}")
                self._parse_errors.append(f"Error parsing recap {recap_file}: {e}")

        return recaps

    def _parse_recap_file(self, file_path: Path) -> RecapFile | None:
        """Parse a recap markdown file."""
        content = file_path.read_text(encoding="utf-8")

        title = ""
        status = "unknown"
        body = content

        # Parse YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                    if frontmatter:
                        status = frontmatter.get("status", "unknown")
                except yaml.YAMLError:
                    pass
                body = parts[2].strip()

        # Extract title from first heading
        lines = body.split("\n")
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        return RecapFile(
            file_path=str(file_path),
            title=title,
            status=status,
            content=body,
        )

    def discover_missions(self, path: Path) -> list[str]:
        """Discover all mission IDs in a .vermas directory.

        Args:
            path: Path to .vermas directory or parent containing .vermas

        Returns:
            List of unique mission IDs found
        """
        vermas_dir = self._find_vermas_directory(path)
        if vermas_dir is None:
            return []

        missions: set[str] = set()
        state_dir = vermas_dir / "state"

        if state_dir.exists():
            for workflow_dir in state_dir.iterdir():
                if not workflow_dir.is_dir():
                    continue
                if workflow_dir.name.startswith("mtg-"):
                    continue

                mission_id, _, _ = self._parse_workflow_id(workflow_dir.name)
                if mission_id:
                    missions.add(mission_id)

        return sorted(missions)

    def get_workflow_executions(
        self, path: Path, mission_id: str | None = None
    ) -> list[WorkflowExecution]:
        """Get workflow execution details for analysis.

        Args:
            path: Path to .vermas directory
            mission_id: Optional filter by mission ID

        Returns:
            List of WorkflowExecution objects
        """
        vermas_dir = self._find_vermas_directory(path)
        if vermas_dir is None:
            return []

        executions: list[WorkflowExecution] = []
        state_dir = vermas_dir / "state"

        if not state_dir.exists():
            return executions

        for workflow_dir in state_dir.iterdir():
            if not workflow_dir.is_dir():
                continue
            if workflow_dir.name.startswith("mtg-"):
                continue

            wf_mission_id, cycle, task_name = self._parse_workflow_id(
                workflow_dir.name
            )

            if mission_id and wf_mission_id != mission_id:
                continue

            signals = self._parse_signals_directory(workflow_dir / "signals")
            if not signals:
                signals = self._parse_events_log(workflow_dir / "events.log")

            if signals:
                timestamps = [s.timestamp for s in signals]
                execution = WorkflowExecution(
                    workflow_id=workflow_dir.name,
                    mission_id=wf_mission_id or "unknown",
                    cycle=cycle or 0,
                    task_name=task_name or "unknown",
                    signals=signals,
                    start_time=min(timestamps),
                    end_time=max(timestamps),
                )
                executions.append(execution)

        return executions
