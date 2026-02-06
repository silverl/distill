"""Tests for narrative generation."""

from datetime import datetime, timedelta, timezone

import pytest

from session_insights.narrative import enrich_narrative, generate_narrative
from session_insights.parsers.models import (
    BaseSession,
    CycleInfo,
    SessionOutcome,
    ToolUsageSummary,
)


@pytest.fixture
def basic_session() -> BaseSession:
    """Create a basic session for testing."""
    start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=25)
    return BaseSession(
        session_id="test-abc123",
        start_time=start,
        end_time=end,
        source="claude-code",
        summary="Help me fix the login bug",
        tools_used=[
            ToolUsageSummary(name="Read", count=5),
            ToolUsageSummary(name="Edit", count=3),
        ],
        outcomes=[
            SessionOutcome(
                description="Fixed authentication check",
                files_modified=["src/auth.py"],
                success=True,
            ),
        ],
        tags=["debugging", "feature"],
        project="my-app",
    )


class TestGenerateNarrative:
    """Tests for generate_narrative function."""

    def test_includes_summary(self, basic_session: BaseSession) -> None:
        narrative = generate_narrative(basic_session)
        assert "Help me fix the login bug" in narrative

    def test_includes_duration(self, basic_session: BaseSession) -> None:
        narrative = generate_narrative(basic_session)
        assert "25 minutes" in narrative

    def test_includes_tools(self, basic_session: BaseSession) -> None:
        narrative = generate_narrative(basic_session)
        assert "Read (5x)" in narrative
        assert "Edit (3x)" in narrative

    def test_includes_outcomes(self, basic_session: BaseSession) -> None:
        narrative = generate_narrative(basic_session)
        assert "Fixed authentication check" in narrative

    def test_includes_files_touched(self, basic_session: BaseSession) -> None:
        narrative = generate_narrative(basic_session)
        assert "1 file(s)" in narrative

    def test_includes_tags(self, basic_session: BaseSession) -> None:
        narrative = generate_narrative(basic_session)
        assert "debugging" in narrative
        assert "feature" in narrative

    def test_brief_duration(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="brief",
            start_time=start,
            end_time=start + timedelta(seconds=30),
            summary="Quick check on the configuration files and settings",
        )
        narrative = generate_narrative(session)
        assert "brief interaction" in narrative

    def test_long_duration(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="long",
            start_time=start,
            end_time=start + timedelta(hours=2, minutes=15),
            summary="Big refactor",
        )
        narrative = generate_narrative(session)
        assert "2h 15m" in narrative

    def test_task_description_preferred(self) -> None:
        session = BaseSession(
            session_id="task",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            summary="Some summary about the project and its features",
            task_description="Implement user auth with JWT token validation",
        )
        narrative = generate_narrative(session)
        assert "Implement user auth" in narrative

    def test_workflow_outcome(self) -> None:
        session = BaseSession(
            session_id="wf",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            summary="Task run",
            cycle_info=CycleInfo(outcome="completed"),
        )
        narrative = generate_narrative(session)
        assert "completed" in narrative

    def test_empty_session(self) -> None:
        session = BaseSession(session_id="empty")
        narrative = generate_narrative(session)
        assert isinstance(narrative, str)

    def test_failed_outcomes(self) -> None:
        session = BaseSession(
            session_id="fail",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            summary="Attempted fix",
            outcomes=[
                SessionOutcome(description="Fix tests", success=False),
            ],
        )
        narrative = generate_narrative(session)
        assert "Incomplete" in narrative
        assert "Fix tests" in narrative

    def test_truncates_long_summary(self) -> None:
        session = BaseSession(
            session_id="long-summary",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            summary="x" * 300,
        )
        narrative = generate_narrative(session)
        assert len(narrative) < 500


class TestEnrichNarrative:
    """Tests for enrich_narrative function."""

    def test_populates_empty_narrative(self, basic_session: BaseSession) -> None:
        assert basic_session.narrative == ""
        enrich_narrative(basic_session)
        assert basic_session.narrative != ""
        assert "Help me fix the login bug" in basic_session.narrative

    def test_does_not_overwrite_existing(self) -> None:
        session = BaseSession(
            session_id="pre",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            summary="Some task",
            narrative="Existing narrative",
        )
        enrich_narrative(session)
        assert session.narrative == "Existing narrative"
