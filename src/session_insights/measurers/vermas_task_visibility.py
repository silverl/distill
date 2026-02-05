"""VerMAS task visibility KPI measurer.

Generates Obsidian notes for VerMAS sessions via the analysis pipeline,
writes them to disk, then reads the generated note files and checks that
each expected metadata section (task description, signals, learnings,
cycle info) is present and non-empty.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from session_insights.core import discover_sessions, parse_session_file
from session_insights.formatters.obsidian import ObsidianFormatter
from session_insights.measurers.base import KPIResult, Measurer
from session_insights.parsers.models import BaseSession

# Sections to check in generated VerMAS note files.
# Each tuple is (field_name, heading/marker to look for in the note).
# "### Description" only appears when task_description is non-empty,
# so it correctly tests "present and non-empty".
VERMAS_NOTE_SECTIONS: list[tuple[str, str]] = [
    ("task_description", "### Description"),
    ("signals", "## Agent Signals"),
    ("learnings", "## Learnings"),
    ("cycle_info", "**Cycle:**"),
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

    # Mission epic
    mission_dir = vermas_dir / "tasks" / "mission-full"
    (mission_dir / "_epic.md").write_text(
        "---\nstatus: in_progress\npriority: high\n---\n# Full Mission\n\nA complete test.\n"
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

    # --- Workflow 2: Partial metadata (no task description file, shared learnings) ---
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


def _generate_vermas_notes_to_disk(
    sessions: list[BaseSession], output_dir: Path
) -> list[Path]:
    """Format VerMAS sessions into Obsidian notes and write them to disk.

    Returns list of generated VerMAS note file paths.
    """
    sessions_dir = output_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    formatter = ObsidianFormatter(include_conversation=False)
    written: list[Path] = []

    vermas_sessions = [s for s in sessions if s.source == "vermas"]
    for session in vermas_sessions:
        note_content = formatter.format_session(session)
        note_path = sessions_dir / f"{session.note_name}.md"
        note_path.write_text(note_content, encoding="utf-8")
        written.append(note_path)

    return written


def score_vermas_note(note_path: Path) -> dict[str, bool]:
    """Score a VerMAS note file for expected metadata sections.

    Returns:
        Dict mapping field name to presence boolean.
    """
    content = note_path.read_text(encoding="utf-8")
    results: dict[str, bool] = {}
    for field_name, marker in VERMAS_NOTE_SECTIONS:
        results[field_name] = marker in content
    return results


class VermasTaskVisibilityMeasurer(Measurer):
    """Measures percentage of expected metadata sections present in generated
    VerMAS notes.

    Workflow: create sample .vermas data -> parse sessions -> format to note
    files on disk -> read VerMAS .md files -> check each for expected sections.
    """

    KPI_NAME = "vermas_task_visibility"
    TARGET = 90.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_note_files(self, note_files: list[Path]) -> KPIResult:
        """Measure visibility from pre-generated VerMAS note files."""
        return self._score_note_files(note_files)

    def _measure_from_directory(self, base: Path) -> KPIResult:
        """Set up sample data, run pipeline, write notes, and score."""
        _create_sample_vermas_dir(base)

        # Parse sessions using the core pipeline
        all_sessions: list[BaseSession] = []
        discovered = discover_sessions(base, sources=["vermas"])
        for src, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, src))

        vermas_sessions = [s for s in all_sessions if s.source == "vermas"]
        if not vermas_sessions:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no vermas sessions parsed"},
            )

        # Generate note files on disk
        output_dir = base / "output"
        note_files = _generate_vermas_notes_to_disk(vermas_sessions, output_dir)

        if not note_files:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no vermas note files generated"},
            )

        return self._score_note_files(note_files)

    def _score_note_files(self, note_files: list[Path]) -> KPIResult:
        """Score VerMAS note files against metadata section checklist."""
        total_fields = 0
        present_fields = 0
        per_note: list[dict[str, object]] = []

        for note_path in note_files:
            scores = score_vermas_note(note_path)

            note_total = len(scores)
            note_present = sum(1 for v in scores.values() if v)
            total_fields += note_total
            present_fields += note_present

            per_note.append(
                {
                    "file": note_path.name,
                    "fields": scores,
                    "present": note_present,
                    "total": note_total,
                }
            )

        value = (present_fields / total_fields * 100) if total_fields > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total_notes": len(note_files),
                "total_fields": total_fields,
                "present_fields": present_fields,
                "per_note": per_note,
            },
        )


if __name__ == "__main__":
    result = VermasTaskVisibilityMeasurer().measure()
    print(result.to_json())
