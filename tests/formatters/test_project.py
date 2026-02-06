"""Tests for project notes formatter."""

from datetime import datetime, timedelta, timezone

import pytest

from session_insights.formatters.project import (
    ProjectFormatter,
    group_sessions_by_project,
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
    tags: list[str] | None = None,
    narrative: str = "",
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
        tags=tags or [],
        narrative=narrative,
        tools_used=[ToolUsageSummary(name="Read", count=3)],
        outcomes=[
            SessionOutcome(
                description="Did work",
                files_modified=["src/main.py"],
                success=True,
            )
        ],
    )


class TestGroupSessionsByProject:
    """Tests for group_sessions_by_project function."""

    def test_groups_by_project(self) -> None:
        sessions = [
            _make_session("a", project="alpha"),
            _make_session("b", project="beta"),
            _make_session("c", project="alpha"),
        ]
        groups = group_sessions_by_project(sessions)
        assert len(groups) == 2
        assert len(groups["alpha"]) == 2
        assert len(groups["beta"]) == 1

    def test_empty_project_grouped_as_unassigned(self) -> None:
        sessions = [
            _make_session("a", project=""),
            _make_session("b", project="alpha"),
        ]
        groups = group_sessions_by_project(sessions)
        assert "(unassigned)" in groups
        assert len(groups["(unassigned)"]) == 1

    def test_empty_input(self) -> None:
        groups = group_sessions_by_project([])
        assert groups == {}

    def test_sorted_by_timestamp(self) -> None:
        sessions = [
            _make_session("later", project="proj", minutes_offset=60),
            _make_session("earlier", project="proj", minutes_offset=0),
        ]
        groups = group_sessions_by_project(sessions)
        assert groups["proj"][0].session_id == "earlier"
        assert groups["proj"][1].session_id == "later"


class TestProjectFormatter:
    """Tests for ProjectFormatter class."""

    @pytest.fixture
    def formatter(self) -> ProjectFormatter:
        return ProjectFormatter()

    @pytest.fixture
    def project_sessions(self) -> list[BaseSession]:
        return [
            _make_session(
                "s1",
                project="my-app",
                summary="Added auth",
                minutes_offset=0,
                tags=["feature"],
                narrative="Implemented authentication module.",
            ),
            _make_session(
                "s2",
                project="my-app",
                summary="Fixed tests",
                minutes_offset=120,
                tags=["testing"],
                narrative="Fixed broken test suite.",
            ),
        ]

    def test_note_name(self) -> None:
        assert ProjectFormatter.note_name("my-app") == "project-my-app"
        assert ProjectFormatter.note_name("My App") == "project-my-app"

    def test_format_project_note_has_frontmatter(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert note.startswith("---")
        assert "project: my-app" in note
        assert "type: project-note" in note
        assert "total_sessions: 2" in note

    def test_format_project_note_has_title(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "# Project: my-app" in note

    def test_format_project_note_has_overview(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Overview" in note
        assert "**Total Sessions:** 2" in note

    def test_format_project_note_has_narrative(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Project Narrative" in note
        assert "Implemented authentication module." in note
        assert "Fixed broken test suite." in note

    def test_format_project_note_has_timeline(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Session Timeline" in note
        assert "Added auth" in note
        assert "Fixed tests" in note

    def test_format_project_note_has_outcomes(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Key Outcomes" in note
        assert "Did work" in note

    def test_format_project_note_has_files(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Files Modified" in note
        assert "`src/main.py`" in note

    def test_format_project_note_has_tool_usage(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Tool Usage" in note
        assert "Read" in note

    def test_format_project_note_has_tags(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Activity Tags" in note
        assert "#feature" in note
        assert "#testing" in note

    def test_format_project_note_has_milestones(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Major Milestones" in note
        # Sessions grouped by week
        assert "2024-W" in note

    def test_format_project_note_has_key_decisions(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Key Decisions" in note
        assert "Did work" in note

    def test_format_project_note_has_related_sessions(
        self, formatter: ProjectFormatter, project_sessions: list[BaseSession]
    ) -> None:
        note = formatter.format_project_note("my-app", project_sessions)
        assert "## Related Sessions" in note
        # Should contain obsidian links to sessions
        assert "[[" in note
