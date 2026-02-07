"""Note content richness KPI measurer.

Generates Obsidian notes via the analysis pipeline, writes them to disk,
then reads each generated note file and scores it against a checklist of
expected content fields.  Reports percentage of fields present across all
notes.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from distill.core import discover_sessions, parse_session_file
from distill.formatters.obsidian import ObsidianFormatter
from distill.measurers.base import KPIResult, Measurer
from distill.parsers.models import BaseSession

# ---------------------------------------------------------------------------
# Field checklists – strings to search for in the generated .md note files
# ---------------------------------------------------------------------------
COMMON_FIELDS: list[tuple[str, str]] = [
    ("has_timestamps", "**Started:**"),
    ("has_duration", "**Duration:**"),
    ("has_tool_list", "## Tools Used"),
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


# ---------------------------------------------------------------------------
# Helpers to create sample source data
# ---------------------------------------------------------------------------
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

    task_dir = vermas_dir / "tasks" / "mission-rich" / "feature"
    task_dir.mkdir(parents=True)
    (task_dir / "implement-feature.md").write_text(
        "---\nstatus: done\n---\n# Implement Feature\n\nBuild the new feature.\n"
    )

    mission_dir = vermas_dir / "tasks" / "mission-rich"
    (mission_dir / "_epic.md").write_text(
        "---\nstatus: in_progress\npriority: high\n---\n# Rich Mission\n\nA rich test mission.\n"
    )

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


def _generate_notes_to_disk(
    sessions: list[BaseSession], output_dir: Path
) -> list[Path]:
    """Format sessions into Obsidian notes and write them to disk.

    Returns list of generated note file paths.
    """
    sessions_dir = output_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    formatter = ObsidianFormatter(include_conversation=True)
    written: list[Path] = []

    for session in sessions:
        note_content = formatter.format_session(session)
        note_path = sessions_dir / f"{session.note_name}.md"
        note_path.write_text(note_content, encoding="utf-8")
        written.append(note_path)

    return written


def _detect_source(note_path: Path, content: str) -> str:
    """Detect the source type from note filename or frontmatter."""
    name = note_path.stem.lower()
    if name.startswith("vermas-"):
        return "vermas"
    if "source: vermas" in content:
        return "vermas"
    if "source: claude" in content:
        return "claude"
    if "source: codex" in content:
        return "codex"
    return "unknown"


def score_note_file(note_path: Path) -> tuple[str, dict[str, bool]]:
    """Read a note file and score it against the checklist.

    Returns:
        Tuple of (source, field_scores).
    """
    content = note_path.read_text(encoding="utf-8")
    source = _detect_source(note_path, content)

    results: dict[str, bool] = {}
    for field_name, search_str in COMMON_FIELDS:
        results[field_name] = search_str in content

    if source == "claude":
        for field_name, search_str in CLAUDE_FIELDS:
            results[field_name] = search_str in content
    elif source == "vermas":
        for field_name, search_str in VERMAS_FIELDS:
            results[field_name] = search_str in content

    return source, results


class NoteContentRichnessMeasurer(Measurer):
    """Measures percentage of expected content fields present in generated notes.

    Workflow: create sample data -> parse sessions -> format to note files on
    disk -> read each .md file -> score against field checklist.
    """

    KPI_NAME = "note_content_richness"
    TARGET = 90.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_note_files(self, note_dir: Path) -> KPIResult:
        """Measure richness from pre-generated note files on disk."""
        note_files = list(note_dir.glob("**/*.md"))
        note_files = [
            f
            for f in note_files
            if f.name != "index.md" and not f.name.startswith("daily-")
        ]
        return self._score_note_files(note_files)

    def _measure_from_directory(self, base: Path) -> KPIResult:
        """Set up sample data, run pipeline, write notes, and score."""
        _create_sample_claude_dir(base)
        _create_sample_vermas_dir(base)

        # Parse sessions using the core pipeline
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

        # Generate note files on disk
        output_dir = base / "output"
        note_files = _generate_notes_to_disk(all_sessions, output_dir)

        if not note_files:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no note files generated"},
            )

        return self._score_note_files(note_files)

    def _score_note_files(self, note_files: list[Path]) -> KPIResult:
        """Read and score each note file."""
        total_fields = 0
        present_fields = 0
        per_note: list[dict[str, object]] = []

        for note_path in note_files:
            source, scores = score_note_file(note_path)

            note_total = len(scores)
            note_present = sum(1 for v in scores.values() if v)
            total_fields += note_total
            present_fields += note_present

            per_note.append(
                {
                    "file": note_path.name,
                    "source": source,
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
                "total_notes": len(note_files),
                "total_fields": total_fields,
                "present_fields": present_fields,
                "per_note": per_note,
            },
        )


if __name__ == "__main__":
    result = NoteContentRichnessMeasurer().measure()
    print(result.to_json())
