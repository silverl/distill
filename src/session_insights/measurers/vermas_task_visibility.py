"""VerMAS task visibility KPI measurer.

Parses generated notes for VerMAS sessions and checks that each expected
metadata field (task_description, signals, learnings, cycle_info) is present
and non-empty.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from session_insights.core import discover_sessions, parse_session_file
from session_insights.measurers.base import KPIResult, Measurer
from session_insights.parsers.models import BaseSession

# Fields to check on VerMAS sessions. Each tuple is
# (field_name, attribute_path_description).
VERMAS_METADATA_FIELDS: list[str] = [
    "task_description",
    "signals",
    "learnings",
    "cycle_info",
]


def _create_sample_vermas_dir(base: Path) -> None:
    """Create a .vermas dir with multiple workflows of varying completeness."""
    vermas_dir = base / ".vermas"

    # --- Workflow 1: Full metadata ---
    wf1 = vermas_dir / "state" / "mission-full-cycle-1-execute-complete-task"
    sig1 = wf1 / "signals"
    sig1.mkdir(parents=True)

    for i, (role, signal, msg) in enumerate(
        [
            ("dev", "done", "Implementation done"),
            ("qa", "approved", "Approved"),
        ]
    ):
        data = {
            "signal_id": f"s{i}",
            "agent_id": f"{role}01",
            "role": role,
            "signal": signal,
            "message": msg,
            "workflow_id": "mission-full-cycle-1-execute-complete-task",
            "created_at": f"2024-06-15T1{i}:00:00",
        }
        (sig1 / f"s{i}.yaml").write_text(yaml.dump(data))

    # Task description file
    task_dir = vermas_dir / "tasks" / "mission-full" / "feature"
    task_dir.mkdir(parents=True)
    (task_dir / "complete-task.md").write_text(
        "---\nstatus: done\n---\n# Complete Task\n\nA fully described task.\n"
    )

    # Agent learnings
    agents_dir = vermas_dir / "knowledge" / "agents"
    agents_dir.mkdir(parents=True)
    learnings = {
        "agents": {
            "general": {
                "learnings": ["Lesson learned"],
                "strengths": [],
                "weaknesses": [],
                "best_practices": [],
            }
        }
    }
    (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings))

    # --- Workflow 2: Partial metadata (no task description, no learnings) ---
    wf2 = vermas_dir / "state" / "mission-partial-cycle-1-execute-sparse-task"
    sig2 = wf2 / "signals"
    sig2.mkdir(parents=True)

    data = {
        "signal_id": "sp1",
        "agent_id": "dev01",
        "role": "dev",
        "signal": "done",
        "message": "Done",
        "workflow_id": "mission-partial-cycle-1-execute-sparse-task",
        "created_at": "2024-06-15T14:00:00",
    }
    (sig2 / "sp1.yaml").write_text(yaml.dump(data))


def _check_field(session: BaseSession, field: str) -> bool:
    """Check whether a metadata field is present and non-empty on a session."""
    value = getattr(session, field, None)
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, list):
        return len(value) > 0
    # For objects (e.g. CycleInfo), presence is enough
    return True


class VermasTaskVisibilityMeasurer(Measurer):
    """Measures percentage of expected metadata fields present in VerMAS sessions."""

    KPI_NAME = "vermas_task_visibility"
    TARGET = 90.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        """Measure visibility from pre-parsed sessions (useful for testing)."""
        vermas_sessions = [s for s in sessions if s.source == "vermas"]
        return self._score_sessions(vermas_sessions)

    def _measure_from_directory(self, base: Path) -> KPIResult:
        """Set up sample data, parse, and score."""
        _create_sample_vermas_dir(base)

        all_sessions: list[BaseSession] = []
        discovered = discover_sessions(base, sources=["vermas"])
        for src, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, src))

        vermas_sessions = [s for s in all_sessions if s.source == "vermas"]
        return self._score_sessions(vermas_sessions)

    def _score_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        """Score VerMAS sessions against metadata field checklist."""
        if not sessions:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no vermas sessions found"},
            )

        total_fields = 0
        present_fields = 0
        per_session: list[dict[str, object]] = []

        for session in sessions:
            field_results: dict[str, bool] = {}
            for field in VERMAS_METADATA_FIELDS:
                present = _check_field(session, field)
                field_results[field] = present
                total_fields += 1
                if present:
                    present_fields += 1

            per_session.append(
                {
                    "session_id": session.session_id[:30],
                    "fields": field_results,
                    "present": sum(1 for v in field_results.values() if v),
                    "total": len(field_results),
                }
            )

        value = (present_fields / total_fields * 100) if total_fields > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total_sessions": len(sessions),
                "total_fields": total_fields,
                "present_fields": present_fields,
                "per_session": per_session,
            },
        )


if __name__ == "__main__":
    result = VermasTaskVisibilityMeasurer().measure()
    print(result.to_json())
