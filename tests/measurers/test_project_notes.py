"""Tests for project_notes KPI measurer."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from session_insights.formatters.project import ProjectFormatter
from session_insights.measurers.base import KPIResult
from session_insights.measurers.project_notes import (
    ProjectNotesMeasurer,
    score_project_note,
)
from session_insights.parsers.models import (
    BaseSession,
    SessionOutcome,
    ToolUsageSummary,
)


def _make_session(
    session_id: str,
    project: str = "",
    summary: str = "test session",
    minutes_offset: int = 0,
) -> BaseSession:
    """Helper to create test sessions."""
    start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=minutes_offset
    )
    return BaseSession(
        session_id=session_id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        source="claude-code",
        summary=summary,
        project=project,
        tags=["feature"],
        tools_used=[ToolUsageSummary(name="Read", count=3)],
        outcomes=[
            SessionOutcome(
                description="Did work",
                files_modified=["src/main.py"],
                success=True,
            )
        ],
    )


def _write_valid_project_note(path: Path) -> Path:
    """Write a project note with all required sections."""
    formatter = ProjectFormatter()
    sessions = [
        _make_session("s1", project="my-app", minutes_offset=0),
        _make_session("s2", project="my-app", minutes_offset=60),
    ]
    content = formatter.format_project_note("my-app", sessions)
    path.write_text(content, encoding="utf-8")
    return path


class TestScoreProjectNote:
    """Tests for the score_project_note function."""

    def test_score_valid_note(self, tmp_path: Path) -> None:
        """A fully valid project note should pass all checks."""
        note = _write_valid_project_note(tmp_path / "project-my-app.md")
        scores = score_project_note(note)
        assert scores["has_timeline"]
        assert scores["has_session_count"]
        assert scores["has_session_links"]
        assert scores["has_milestones"]
        assert scores["has_key_decisions"]
        assert scores["has_related_sessions"]

    def test_score_empty_note(self, tmp_path: Path) -> None:
        """An empty note should fail all checks."""
        note_path = tmp_path / "project-empty.md"
        note_path.write_text("", encoding="utf-8")
        scores = score_project_note(note_path)
        assert not scores["has_timeline"]
        assert not scores["has_session_count"]
        assert not scores["has_session_links"]
        assert not scores["has_milestones"]
        assert not scores["has_key_decisions"]
        assert not scores["has_related_sessions"]

    def test_score_partial_note(self, tmp_path: Path) -> None:
        """A note with only a timeline section should partially pass."""
        content = "# Project: test\n\n## Session Timeline\n\nSome content\n"
        note_path = tmp_path / "project-test.md"
        note_path.write_text(content, encoding="utf-8")
        scores = score_project_note(note_path)
        assert scores["has_timeline"]
        assert not scores["has_session_count"]
        assert not scores["has_session_links"]


class TestProjectNotesMeasurer:
    """Tests for the ProjectNotesMeasurer class."""

    def test_result_is_kpi_result(self) -> None:
        """Measurer returns a KPIResult with correct KPI name."""
        measurer = ProjectNotesMeasurer()
        result = measurer.measure()
        assert isinstance(result, KPIResult)
        assert result.kpi == "project_notes"
        assert result.target == 100.0

    def test_value_in_range(self) -> None:
        """Measured value is between 0 and 100."""
        measurer = ProjectNotesMeasurer()
        result = measurer.measure()
        assert 0.0 <= result.value <= 100.0

    def test_details_contain_note_info(self) -> None:
        """Details include project note counts or error when no projects detected."""
        measurer = ProjectNotesMeasurer()
        result = measurer.measure()
        # Sample data may not produce project-tagged sessions, so either
        # we get note counts or an error explaining why.
        assert "total_project_notes" in result.details or "error" in result.details

    def test_json_serialization(self) -> None:
        """Result serializes to valid JSON."""
        measurer = ProjectNotesMeasurer()
        result = measurer.measure()
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["kpi"] == "project_notes"
        assert isinstance(parsed["value"], float)

    def test_measure_from_output_with_valid_notes(self, tmp_path: Path) -> None:
        """measure_from_output scores files in projects/ directory."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        _write_valid_project_note(projects_dir / "project-my-app.md")

        measurer = ProjectNotesMeasurer()
        result = measurer.measure_from_output(tmp_path)
        assert result.value == 100.0
        assert result.details["total_project_notes"] == 1
        assert result.details["valid_notes"] == 1

    def test_measure_from_output_no_projects_dir(self, tmp_path: Path) -> None:
        """Returns 0 when projects/ directory doesn't exist."""
        measurer = ProjectNotesMeasurer()
        result = measurer.measure_from_output(tmp_path)
        assert result.value == 0.0
        assert "error" in result.details

    def test_measure_from_output_empty_dir(self, tmp_path: Path) -> None:
        """Returns 0 when projects/ directory is empty."""
        (tmp_path / "projects").mkdir()
        measurer = ProjectNotesMeasurer()
        result = measurer.measure_from_output(tmp_path)
        assert result.value == 0.0
        assert "error" in result.details

    def test_measure_from_output_mixed_validity(self, tmp_path: Path) -> None:
        """Reports correct percentage when some notes are invalid."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        # Valid note
        _write_valid_project_note(projects_dir / "project-valid.md")

        # Invalid note (missing required sections)
        (projects_dir / "project-invalid.md").write_text(
            "# Just a title\n\nNo sections here.\n", encoding="utf-8"
        )

        measurer = ProjectNotesMeasurer()
        result = measurer.measure_from_output(tmp_path)
        assert result.value == 50.0
        assert result.details["total_project_notes"] == 2
        assert result.details["valid_notes"] == 1
