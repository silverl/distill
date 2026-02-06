"""Project detection KPI measurer.

Creates sample sessions via the analysis pipeline and measures
the percentage that have a non-empty project field.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from session_insights.core import discover_sessions, parse_session_file
from session_insights.measurers.base import KPIResult, Measurer
from session_insights.parsers.models import BaseSession


def _create_sample_data(base: Path) -> None:
    """Create sample .claude, .codex, and .vermas dirs with sessions."""
    # Claude sessions with cwd (should detect project)
    project_dir = base / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    now = datetime.now(tz=timezone.utc)
    entries = [
        {
            "type": "user",
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "cwd": "/home/user/projects/my-app",
            "sessionId": "sess-with-cwd",
            "message": {"content": "Fix the auth bug"},
        },
        {
            "type": "assistant",
            "timestamp": (now - timedelta(hours=2) + timedelta(minutes=1)).isoformat(),
            "message": {"content": "I will fix it."},
        },
    ]
    session_file = project_dir / "sess-with-cwd.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    # Claude session without cwd (should NOT detect project)
    entries_no_cwd = [
        {
            "type": "user",
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "sessionId": "sess-no-cwd",
            "message": {"content": "Help me with something"},
        },
        {
            "type": "assistant",
            "timestamp": (now - timedelta(minutes=55)).isoformat(),
            "message": {"content": "Sure."},
        },
    ]
    session_file2 = project_dir / "sess-no-cwd.jsonl"
    with session_file2.open("w", encoding="utf-8") as f:
        for entry in entries_no_cwd:
            f.write(json.dumps(entry) + "\n")

    # VerMAS workflow (should detect project from workflow/mission name)
    vermas_dir = base / ".vermas"
    wf = vermas_dir / "state" / "mission-proj-cycle-1-execute-build-feature"
    sig_dir = wf / "signals"
    sig_dir.mkdir(parents=True)

    data = {
        "signal_id": "sig1",
        "agent_id": "dev01",
        "role": "dev",
        "signal": "done",
        "message": "Done",
        "workflow_id": "mission-proj-cycle-1-execute-build-feature",
        "created_at": "2024-06-15T10:00:00",
    }
    (sig_dir / "sig1.yaml").write_text(yaml.dump(data))

    task_dir = vermas_dir / "tasks" / "mission-proj" / "feature"
    task_dir.mkdir(parents=True)
    (task_dir / "build-feature.md").write_text(
        "---\nstatus: done\n---\n# Build Feature\n\nBuild it.\n"
    )
    mission_dir = vermas_dir / "tasks" / "mission-proj"
    (mission_dir / "_epic.md").write_text(
        "---\nstatus: in_progress\n---\n# Project Mission\n"
    )

    agents_dir = vermas_dir / "knowledge" / "agents"
    agents_dir.mkdir(parents=True)
    learnings = {
        "agents": {
            "general": {
                "learnings": [],
                "strengths": [],
                "weaknesses": [],
                "best_practices": [],
            }
        }
    }
    (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings))


class ProjectDetectionMeasurer(Measurer):
    """Measures percentage of parsed sessions with a detected project."""

    KPI_NAME = "project_detection"
    TARGET = 80.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        """Measure project detection rate from pre-parsed sessions."""
        return self._score_sessions(sessions)

    def _measure_from_directory(self, base: Path) -> KPIResult:
        _create_sample_data(base)

        all_sessions: list[BaseSession] = []
        discovered = discover_sessions(base, sources=None)
        for src, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, src))

        if not all_sessions:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no sessions parsed"},
            )

        return self._score_sessions(all_sessions)

    def _score_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        total = len(sessions)
        detected = sum(1 for s in sessions if s.project)
        value = (detected / total * 100) if total > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total_sessions": total,
                "with_project": detected,
                "without_project": total - detected,
            },
        )


if __name__ == "__main__":
    result = ProjectDetectionMeasurer().measure()
    print(result.to_json())
