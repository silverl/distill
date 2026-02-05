"""Note content richness KPI measurer.

Generates notes via the CLI pipeline and scores each note against a checklist
of expected content fields. Reports percentage of fields present across all
notes.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from session_insights.core import analyze, discover_sessions, parse_session_file
from session_insights.formatters.obsidian import ObsidianFormatter
from session_insights.measurers.base import KPIResult, Measurer
from session_insights.parsers.models import BaseSession

# Checklist fields to look for in generated notes.
# Each tuple is (field_name, search_string_or_callable).
COMMON_FIELDS: list[tuple[str, str]] = [
    ("has_timestamps", "start_time:"),
    ("has_duration", "duration"),
    ("has_tool_list", "## Tools"),
    ("has_outcomes", "## Outcomes"),
]

CLAUDE_FIELDS: list[tuple[str, str]] = [
    ("has_conversation_summary", "## Conversation"),
]

VERMAS_FIELDS: list[tuple[str, str]] = [
    ("has_vermas_task_details", "## Task Details"),
    ("has_vermas_signals", "## Agent Signals"),
    ("has_vermas_learnings", "## Learnings"),
]


def _create_sample_claude_dir(base: Path) -> None:
    """Create a .claude dir with sample sessions."""
    project_dir = base / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    now = datetime.now(tz=timezone.utc)
    entries = [
        {
            "type": "user",
            "message": {"content": "Refactor the auth module"},
            "timestamp": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "I will refactor the auth module for you."},
            "timestamp": (now - timedelta(hours=2) + timedelta(minutes=1)).isoformat(),
        },
        {
            "type": "user",
            "message": {"content": "Add unit tests for the login module"},
            "timestamp": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "Adding tests now."},
            "timestamp": (now - timedelta(minutes=55)).isoformat(),
        },
    ]
    session_file = project_dir / "session.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _create_sample_vermas_dir(base: Path) -> None:
    """Create a .vermas dir with sample workflow data that has rich metadata."""
    vermas_dir = base / ".vermas"

    # Workflow with signals
    workflow_dir = vermas_dir / "state" / "mission-rich-cycle-1-execute-implement-feature"
    signals_dir = workflow_dir / "signals"
    signals_dir.mkdir(parents=True)

    for i, (role, signal, msg) in enumerate(
        [
            ("dev", "done", "Implementation complete"),
            ("qa", "approved", "Tests pass, looks good"),
        ]
    ):
        signal_data = {
            "signal_id": f"sig{i}",
            "agent_id": f"{role}01",
            "role": role,
            "signal": signal,
            "message": msg,
            "workflow_id": "mission-rich-cycle-1-execute-implement-feature",
            "created_at": f"2024-06-15T1{i}:00:00",
        }
        (signals_dir / f"sig{i}.yaml").write_text(yaml.dump(signal_data))

    # Task description
    task_dir = vermas_dir / "tasks" / "mission-rich" / "feature"
    task_dir.mkdir(parents=True)
    (task_dir / "implement-feature.md").write_text(
        "---\nstatus: done\n---\n# Implement Feature\n\nBuild the new feature.\n"
    )

    # Mission epic
    mission_dir = vermas_dir / "tasks" / "mission-rich"
    (mission_dir / "_epic.md").write_text(
        "---\nstatus: in_progress\npriority: high\n---\n# Rich Mission\n\nA rich test mission.\n"
    )

    # Agent learnings
    agents_dir = vermas_dir / "knowledge" / "agents"
    agents_dir.mkdir(parents=True)
    learnings_data = {
        "agents": {
            "general": {
                "learnings": ["Tests are important"],
                "strengths": ["Fast"],
                "weaknesses": [],
                "best_practices": ["Write tests first"],
            }
        }
    }
    (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings_data))


def _score_note(content: str, source: str) -> dict[str, bool]:
    """Score a note against the field checklist for its source type."""
    results: dict[str, bool] = {}

    for field_name, search_str in COMMON_FIELDS:
        results[field_name] = search_str.lower() in content.lower()

    if source == "claude":
        for field_name, search_str in CLAUDE_FIELDS:
            results[field_name] = search_str.lower() in content.lower()
    elif source == "vermas":
        for field_name, search_str in VERMAS_FIELDS:
            results[field_name] = search_str.lower() in content.lower()

    return results


class NoteContentRichnessMeasurer(Measurer):
    """Measures percentage of expected content fields present in generated notes."""

    KPI_NAME = "note_content_richness"
    TARGET = 90.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        """Measure richness from pre-parsed sessions (useful for testing)."""
        return self._score_sessions(sessions)

    def _measure_from_directory(self, base: Path) -> KPIResult:
        """Set up sample data, parse, format, and score."""
        _create_sample_claude_dir(base)
        _create_sample_vermas_dir(base)

        all_sessions: list[BaseSession] = []
        discovered = discover_sessions(base, sources=None)
        for src, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, src))

        return self._score_sessions(all_sessions)

    def _score_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        """Format sessions to notes and score them."""
        if not sessions:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no sessions found"},
            )

        formatter = ObsidianFormatter(include_conversation=True)

        total_fields = 0
        present_fields = 0
        per_note: list[dict[str, object]] = []

        for session in sessions:
            note_content = formatter.format_session(session)
            scores = _score_note(note_content, session.source)

            note_total = len(scores)
            note_present = sum(1 for v in scores.values() if v)
            total_fields += note_total
            present_fields += note_present

            per_note.append(
                {
                    "session_id": session.session_id[:20],
                    "source": session.source,
                    "fields_present": note_present,
                    "fields_total": note_total,
                    "scores": scores,
                }
            )

        value = (present_fields / total_fields * 100) if total_fields > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total_notes": len(sessions),
                "total_fields": total_fields,
                "present_fields": present_fields,
                "per_note": per_note,
            },
        )


if __name__ == "__main__":
    result = NoteContentRichnessMeasurer().measure()
    print(result.to_json())
