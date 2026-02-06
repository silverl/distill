"""Tests for narrative quality scorer and improved narrative generation."""

from datetime import datetime, timedelta, timezone

import pytest

from session_insights.measurers.narrative_quality import (
    NarrativeQualityMeasurer,
    score_narrative,
)
from session_insights.narrative import (
    _is_low_quality_summary,
    _generate_metadata_narrative,
    _sanitize_text,
    enrich_narrative,
    generate_narrative,
)
from session_insights.parsers.models import (
    BaseSession,
    CycleInfo,
    SessionOutcome,
    ToolUsageSummary,
)


# ---------------------------------------------------------------------------
# Tests for score_narrative
# ---------------------------------------------------------------------------


class TestScoreNarrative:
    """Tests for the score_narrative function."""

    def test_good_narrative_passes(self) -> None:
        text = "45-minute session in vermas using Bash, Read, Edit. Modified 15 files across the workflow engine."
        ok, reasons = score_narrative(text)
        assert ok is True
        assert reasons == []

    def test_empty_narrative_fails(self) -> None:
        ok, reasons = score_narrative("")
        assert ok is False
        assert "empty_narrative" in reasons

    def test_none_narrative_fails(self) -> None:
        ok, reasons = score_narrative(None)  # type: ignore[arg-type]
        assert ok is False
        assert "empty_narrative" in reasons

    def test_whitespace_only_fails(self) -> None:
        ok, reasons = score_narrative("   \n  ")
        assert ok is False
        assert "empty_narrative" in reasons

    def test_xml_tags_rejected(self) -> None:
        text = "<command-message>Please analyze the code</command-message>"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "contains_xml_tags" in reasons

    def test_system_reminder_rejected(self) -> None:
        text = "<system-reminder>You are an AI assistant that helps with coding</system-reminder>"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "contains_xml_tags" in reasons

    def test_short_narrative_rejected(self) -> None:
        text = "Fixed bug"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "too_short" in reasons

    def test_exactly_10_words_passes(self) -> None:
        text = "This is a ten word sentence that should barely pass check"
        ok, reasons = score_narrative(text)
        assert ok is True

    def test_9_words_fails(self) -> None:
        text = "This is a nine word sentence that barely fails"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "too_short" in reasons

    def test_file_path_rejected(self) -> None:
        text = "src/auth.py"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "just_file_path" in reasons

    def test_tool_name_rejected(self) -> None:
        text = "Read"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "just_tool_name" in reasons

    def test_literal_command_rejected(self) -> None:
        text = "analyze home"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "literal_command" in reasons

    def test_init_command_rejected(self) -> None:
        text = "init"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "literal_command" in reasons

    def test_slash_command_rejected(self) -> None:
        text = "/help"
        ok, reasons = score_narrative(text)
        assert ok is False

    def test_multiple_failures(self) -> None:
        text = "<tag>init</tag>"
        ok, reasons = score_narrative(text)
        assert ok is False
        assert "contains_xml_tags" in reasons
        assert "too_short" in reasons


# ---------------------------------------------------------------------------
# Tests for _is_low_quality_summary
# ---------------------------------------------------------------------------


class TestIsLowQualitySummary:
    """Tests for the _is_low_quality_summary helper."""

    def test_empty_is_low_quality(self) -> None:
        assert _is_low_quality_summary("") is True

    def test_short_is_low_quality(self) -> None:
        assert _is_low_quality_summary("init") is True

    def test_xml_is_low_quality(self) -> None:
        assert _is_low_quality_summary("something <tag> here and more words") is True

    def test_file_path_is_low_quality(self) -> None:
        assert _is_low_quality_summary("src/main.py") is True

    def test_good_summary_passes(self) -> None:
        assert _is_low_quality_summary("Help me fix the login bug in the auth module") is False


# ---------------------------------------------------------------------------
# Tests for _sanitize_text
# ---------------------------------------------------------------------------


class TestSanitizeText:
    """Tests for the _sanitize_text helper."""

    def test_strips_xml_tags(self) -> None:
        result = _sanitize_text("<system-reminder>Hello world</system-reminder>")
        assert result == "Hello world"

    def test_collapses_whitespace(self) -> None:
        result = _sanitize_text("hello   world   foo")
        assert result == "hello world foo"

    def test_preserves_clean_text(self) -> None:
        result = _sanitize_text("A clean sentence about code.")
        assert result == "A clean sentence about code."


# ---------------------------------------------------------------------------
# Tests for improved narrative generation
# ---------------------------------------------------------------------------


class TestImprovedNarrativeGeneration:
    """Tests for the improved generate_narrative function."""

    def test_good_summary_used(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="good",
            start_time=start,
            end_time=start + timedelta(minutes=25),
            summary="Help me fix the login bug in the auth module",
        )
        narrative = generate_narrative(session)
        assert "login bug" in narrative
        assert "25 minutes" in narrative

    def test_xml_summary_falls_back_to_metadata(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="xml",
            start_time=start,
            end_time=start + timedelta(minutes=45),
            summary="<command-message>analyze the code</command-message>",
            project="vermas",
            tools_used=[
                ToolUsageSummary(name="Bash", count=10),
                ToolUsageSummary(name="Read", count=8),
                ToolUsageSummary(name="Edit", count=5),
            ],
            outcomes=[
                SessionOutcome(
                    description="Modified 15 files",
                    files_modified=[f"src/mod{i}.py" for i in range(15)],
                ),
            ],
        )
        narrative = generate_narrative(session)
        # Should NOT contain XML tags
        assert "<" not in narrative
        # Should contain metadata-based info
        assert "vermas" in narrative
        assert "Bash" in narrative

    def test_short_summary_falls_back_to_metadata(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="short",
            start_time=start,
            end_time=start + timedelta(minutes=30),
            summary="init",
            project="my-project",
            tools_used=[ToolUsageSummary(name="Read", count=3)],
        )
        narrative = generate_narrative(session)
        assert "my-project" in narrative
        assert "Read" in narrative

    def test_metadata_narrative_with_duration(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="dur",
            start_time=start,
            end_time=start + timedelta(minutes=45),
            project="vermas",
            tools_used=[
                ToolUsageSummary(name="Bash", count=10),
                ToolUsageSummary(name="Read", count=8),
                ToolUsageSummary(name="Edit", count=5),
            ],
        )
        narrative = _generate_metadata_narrative(session)
        assert "45-minute" in narrative
        assert "vermas" in narrative
        assert "Bash" in narrative

    def test_metadata_narrative_brief_session(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="brief",
            start_time=start,
            end_time=start + timedelta(seconds=30),
        )
        narrative = _generate_metadata_narrative(session)
        assert "Brief" in narrative

    def test_metadata_narrative_long_session(self) -> None:
        start = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        session = BaseSession(
            session_id="long",
            start_time=start,
            end_time=start + timedelta(hours=2, minutes=15),
            project="my-app",
        )
        narrative = _generate_metadata_narrative(session)
        assert "2h 15m" in narrative
        assert "my-app" in narrative

    def test_metadata_narrative_with_outcomes(self) -> None:
        session = BaseSession(
            session_id="out",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            outcomes=[
                SessionOutcome(
                    description="Fixed auth bug",
                    files_modified=["src/auth.py", "tests/test_auth.py"],
                ),
            ],
        )
        narrative = _generate_metadata_narrative(session)
        assert "2 file(s)" in narrative
        assert "Fixed auth bug" in narrative

    def test_metadata_narrative_with_cycle_info(self) -> None:
        session = BaseSession(
            session_id="cycle",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            cycle_info=CycleInfo(task_name="fix-login", outcome="completed"),
        )
        narrative = _generate_metadata_narrative(session)
        assert "fix-login" in narrative
        assert "completed" in narrative

    def test_metadata_narrative_no_data(self) -> None:
        session = BaseSession(session_id="empty")
        narrative = _generate_metadata_narrative(session)
        assert "Coding session" in narrative

    def test_enrich_replaces_low_quality_narrative(self) -> None:
        session = BaseSession(
            session_id="enrich",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
            narrative="init",
            project="test-project",
            tools_used=[ToolUsageSummary(name="Bash", count=5)],
        )
        enrich_narrative(session)
        assert "init" != session.narrative
        assert "test-project" in session.narrative

    def test_enrich_preserves_good_narrative(self) -> None:
        session = BaseSession(
            session_id="keep",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            narrative="A long detailed narrative about the coding session with sufficient detail",
        )
        enrich_narrative(session)
        assert session.narrative == "A long detailed narrative about the coding session with sufficient detail"

    def test_task_description_preferred_over_summary(self) -> None:
        session = BaseSession(
            session_id="task",
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            summary="<command-message>raw prompt</command-message>",
            task_description="Implement user authentication with JWT tokens",
        )
        narrative = generate_narrative(session)
        assert "JWT tokens" in narrative
        assert "<" not in narrative


# ---------------------------------------------------------------------------
# Tests for NarrativeQualityMeasurer
# ---------------------------------------------------------------------------


class TestNarrativeQualityMeasurer:
    """Tests for the NarrativeQualityMeasurer class."""

    def _make_session(
        self,
        session_id: str,
        narrative: str = "",
        **kwargs: object,
    ) -> BaseSession:
        return BaseSession(
            session_id=session_id,
            start_time=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            narrative=narrative,
            **kwargs,
        )

    def test_all_good_narratives(self) -> None:
        sessions = [
            self._make_session("s1", narrative="45-minute session in vermas using Bash, Read, Edit to fix authentication."),
            self._make_session("s2", narrative="Implemented the new user registration flow with email verification and testing."),
        ]
        measurer = NarrativeQualityMeasurer(sessions)
        result = measurer.measure()
        assert result.value == 100.0
        assert result.kpi == "narrative_quality"

    def test_all_bad_narratives(self) -> None:
        sessions = [
            self._make_session("s1", narrative="init"),
            self._make_session("s2", narrative="<tag>raw</tag>"),
        ]
        measurer = NarrativeQualityMeasurer(sessions)
        result = measurer.measure()
        assert result.value == 0.0

    def test_mixed_quality(self) -> None:
        sessions = [
            self._make_session("s1", narrative="A good narrative about the coding session that passes quality checks."),
            self._make_session("s2", narrative="init"),
            self._make_session("s3", narrative="Another passing narrative about fixing bugs in the authentication module."),
            self._make_session("s4", narrative="<tag>bad</tag>"),
        ]
        measurer = NarrativeQualityMeasurer(sessions)
        result = measurer.measure()
        # 2 out of 4 pass = 50%
        assert result.value == 50.0

    def test_empty_sessions(self) -> None:
        measurer = NarrativeQualityMeasurer([])
        result = measurer.measure()
        assert result.value == 0.0
        assert "error" in result.details

    def test_generates_narrative_when_missing(self) -> None:
        """When narrative is empty, the measurer generates one from session metadata."""
        sessions = [
            self._make_session(
                "s1",
                narrative="",
                project="my-project",
                tools_used=[ToolUsageSummary(name="Bash", count=5), ToolUsageSummary(name="Read", count=3)],
                end_time=datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
            ),
        ]
        measurer = NarrativeQualityMeasurer(sessions)
        result = measurer.measure()
        # The generated narrative from metadata should pass
        assert result.value == 100.0

    def test_result_details_structure(self) -> None:
        sessions = [
            self._make_session("s1", narrative="A good detailed narrative about a coding session with tests and fixes."),
        ]
        measurer = NarrativeQualityMeasurer(sessions)
        result = measurer.measure()
        assert "total_sessions" in result.details
        assert "passed" in result.details
        assert "failed" in result.details
        assert "failure_reasons" in result.details
        assert "per_session" in result.details

    def test_target_is_80(self) -> None:
        measurer = NarrativeQualityMeasurer()
        result = measurer.measure()
        assert result.target == 80.0
