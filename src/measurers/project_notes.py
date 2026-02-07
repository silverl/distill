"""Project notes KPI measurer.

Generates project notes via the analysis pipeline, writes them to disk,
then reads each generated note file and checks that it contains the
expected sections: timeline, session count, and session links.
Reports percentage of projects with valid notes.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from distill.core import (
    discover_sessions,
    generate_project_notes,
    parse_session_file,
)
from distill.formatters.project import group_sessions_by_project
from distill.measurers.base import KPIResult, Measurer
from distill.parsers.models import BaseSession

# Sections required in each project note for it to be considered valid.
PROJECT_NOTE_SECTIONS: list[tuple[str, str]] = [
    ("has_timeline", "## Session Timeline"),
    ("has_session_count", "**Total Sessions:**"),
    ("has_session_links", "[["),
    ("has_milestones", "## Major Milestones"),
    ("has_key_decisions", "## Key Decisions"),
    ("has_related_sessions", "## Related Sessions"),
]


def _create_sample_data(base: Path) -> None:
    """Create sample .claude and .vermas dirs with sessions in multiple projects."""
    # Claude sessions across two projects
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

    # VerMAS workflow
    vermas_dir = base / ".vermas"
    wf = vermas_dir / "state" / "mission-proj-cycle-1-execute-build-feature"
    sig_dir = wf / "signals"
    sig_dir.mkdir(parents=True)

    for i, (role, signal, msg) in enumerate(
        [
            ("dev", "done", "Implementation complete"),
            ("qa", "approved", "Tests pass"),
        ]
    ):
        data = {
            "signal_id": f"sig{i}",
            "agent_id": f"{role}01",
            "role": role,
            "signal": signal,
            "message": msg,
            "workflow_id": "mission-proj-cycle-1-execute-build-feature",
            "created_at": f"2024-06-15T1{i}:00:00",
        }
        (sig_dir / f"sig{i}.yaml").write_text(yaml.dump(data))

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
                "learnings": ["Tests matter"],
                "strengths": [],
                "weaknesses": [],
                "best_practices": [],
            }
        }
    }
    (agents_dir / "agent-learnings.yaml").write_text(yaml.dump(learnings))


def _generate_project_notes_to_disk(
    sessions: list[BaseSession], output_dir: Path
) -> list[Path]:
    """Generate project notes to disk using the core pipeline.

    Returns list of generated project note file paths.
    """
    return generate_project_notes(sessions, output_dir)


def score_project_note(note_path: Path) -> dict[str, bool]:
    """Score a project note file for expected sections.

    Returns:
        Dict mapping field name to presence boolean.
    """
    content = note_path.read_text(encoding="utf-8")
    results: dict[str, bool] = {}
    for field_name, marker in PROJECT_NOTE_SECTIONS:
        results[field_name] = marker in content
    return results


class ProjectNotesMeasurer(Measurer):
    """Measures percentage of projects with valid notes.

    Workflow: create sample data -> parse sessions -> group by project ->
    generate project notes to disk -> read each .md file -> score
    against expected section checklist.
    """

    KPI_NAME = "project_notes"
    TARGET = 100.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_output(self, output_dir: Path) -> KPIResult:
        """Measure from pre-generated output directory.

        Expects output_dir/projects/ to contain project note files.
        """
        projects_dir = output_dir / "projects"
        if not projects_dir.exists():
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "projects/ directory not found"},
            )

        note_files = list(projects_dir.glob("project-*.md"))
        if not note_files:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no project note files found", "dir": str(projects_dir)},
            )

        return self._score_note_files(note_files)

    def _measure_from_directory(self, base: Path) -> KPIResult:
        """Set up sample data, parse, generate notes, and score."""
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

        # Count real projects (excluding pseudo-projects)
        groups = group_sessions_by_project(all_sessions)
        real_projects = {
            k for k in groups if k not in ("(unknown)", "(unassigned)")
        }

        if not real_projects:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no real projects detected"},
            )

        output_dir = base / "output"
        note_files = _generate_project_notes_to_disk(all_sessions, output_dir)

        if not note_files:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no project note files generated"},
            )

        return self._score_note_files(note_files, expected_projects=real_projects)

    def _score_note_files(
        self,
        note_files: list[Path],
        expected_projects: set[str] | None = None,
    ) -> KPIResult:
        """Score project note files against expected sections."""
        valid_count = 0
        per_note: list[dict[str, object]] = []

        for note_path in note_files:
            scores = score_project_note(note_path)
            is_valid = all(scores.values())
            if is_valid:
                valid_count += 1

            per_note.append(
                {
                    "file": note_path.name,
                    "scores": scores,
                    "valid": is_valid,
                }
            )

        total = len(note_files)

        # When expected_projects is provided, use it as denominator to enforce
        # per-project coverage: value = valid_notes / expected_projects * 100
        if expected_projects is not None:
            denominator = len(expected_projects)
        else:
            denominator = total

        value = (valid_count / denominator * 100) if denominator > 0 else 0.0

        details: dict[str, object] = {
            "total_project_notes": total,
            "valid_notes": valid_count,
            "per_note": per_note,
        }
        if expected_projects is not None:
            details["expected_projects"] = len(expected_projects)
            details["coverage"] = (
                total / len(expected_projects) * 100
                if expected_projects
                else 0.0
            )

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details=details,
        )


if __name__ == "__main__":
    result = ProjectNotesMeasurer().measure()
    print(result.to_json())
