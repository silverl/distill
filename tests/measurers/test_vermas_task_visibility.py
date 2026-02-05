"""Tests for vermas_task_visibility KPI measurer."""

import json
from datetime import datetime, timezone

import pytest

from session_insights.measurers.base import KPIResult
from session_insights.measurers.vermas_task_visibility import (
    VermasTaskVisibilityMeasurer,
    _check_field,
)
from session_insights.parsers.models import (
    AgentLearning,
    AgentSignal,
    BaseSession,
    CycleInfo,
)


class TestCheckField:
    """Tests for the field presence checker."""

    def test_string_field_present(self) -> None:
        """Non-empty string field returns True."""
        session = BaseSession(
            session_id="test",
            timestamp=datetime.now(tz=timezone.utc),
            task_description="Do something",
        )
        assert _check_field(session, "task_description") is True

    def test_string_field_empty(self) -> None:
        """Empty string field returns False."""
        session = BaseSession(
            session_id="test",
            timestamp=datetime.now(tz=timezone.utc),
            task_description="",
        )
        assert _check_field(session, "task_description") is False

    def test_list_field_present(self) -> None:
        """Non-empty list field returns True."""
        now = datetime.now(tz=timezone.utc)
        session = BaseSession(
            session_id="test",
            timestamp=now,
            signals=[
                AgentSignal(
                    signal_id="s1",
                    agent_id="dev",
                    role="dev",
                    signal="done",
                    message="Done",
                    timestamp=now,
                    workflow_id="test",
                )
            ],
        )
        assert _check_field(session, "signals") is True

    def test_list_field_empty(self) -> None:
        """Empty list field returns False."""
        session = BaseSession(
            session_id="test",
            timestamp=datetime.now(tz=timezone.utc),
        )
        assert _check_field(session, "signals") is False

    def test_object_field_present(self) -> None:
        """Present object field returns True."""
        session = BaseSession(
            session_id="test",
            timestamp=datetime.now(tz=timezone.utc),
            cycle_info=CycleInfo(mission_id="abc", cycle=1),
        )
        assert _check_field(session, "cycle_info") is True

    def test_object_field_none(self) -> None:
        """None object field returns False."""
        session = BaseSession(
            session_id="test",
            timestamp=datetime.now(tz=timezone.utc),
        )
        assert _check_field(session, "cycle_info") is False

    def test_nonexistent_field(self) -> None:
        """Non-existent attribute returns False."""
        session = BaseSession(
            session_id="test",
            timestamp=datetime.now(tz=timezone.utc),
        )
        assert _check_field(session, "nonexistent_field") is False


class TestVermasTaskVisibilityMeasurer:
    """Tests for the vermas_task_visibility measurer."""

    def test_result_is_kpi_result(self) -> None:
        """Measurer returns a KPIResult."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        assert isinstance(result, KPIResult)
        assert result.kpi == "vermas_task_visibility"
        assert result.target == 90.0

    def test_value_in_range(self) -> None:
        """Measured value is between 0 and 100."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        assert 0.0 <= result.value <= 100.0

    def test_details_contain_session_info(self) -> None:
        """Details include per-session field data."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        assert "total_sessions" in result.details
        assert "per_session" in result.details

    def test_json_serialization(self) -> None:
        """Result serializes to valid JSON."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["kpi"] == "vermas_task_visibility"

    def test_measure_from_sessions_empty(self) -> None:
        """Empty session list gives 0% value."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_sessions([])
        assert result.value == 0.0

    def test_full_metadata_session(self) -> None:
        """Session with all metadata fields should score 100%."""
        now = datetime.now(tz=timezone.utc)
        session = BaseSession(
            session_id="full-vermas",
            timestamp=now,
            source="vermas",
            task_description="Implement feature X",
            signals=[
                AgentSignal(
                    signal_id="s1",
                    agent_id="dev01",
                    role="dev",
                    signal="done",
                    message="Done",
                    timestamp=now,
                    workflow_id="test",
                ),
            ],
            learnings=[
                AgentLearning(agent="general", learnings=["Write tests"]),
            ],
            cycle_info=CycleInfo(
                mission_id="abc",
                cycle=1,
                task_name="feature-x",
            ),
        )
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_sessions([session])
        assert result.value == 100.0

    def test_partial_metadata_session(self) -> None:
        """Session with some missing fields scores < 100%."""
        now = datetime.now(tz=timezone.utc)
        session = BaseSession(
            session_id="partial-vermas",
            timestamp=now,
            source="vermas",
            task_description="",  # empty
            signals=[
                AgentSignal(
                    signal_id="s1",
                    agent_id="dev01",
                    role="dev",
                    signal="done",
                    message="Done",
                    timestamp=now,
                    workflow_id="test",
                ),
            ],
            # no learnings
            # no cycle_info
        )
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_sessions([session])
        assert result.value == 25.0  # 1 of 4 fields present (signals)

    def test_non_vermas_sessions_filtered(self) -> None:
        """Non-vermas sessions should be filtered out."""
        now = datetime.now(tz=timezone.utc)
        session = BaseSession(
            session_id="claude-session",
            timestamp=now,
            source="claude",
            task_description="Some task",
        )
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_sessions([session])
        assert result.value == 0.0
        assert "error" in result.details

    def test_multiple_sessions_averaged(self) -> None:
        """Score is averaged across all sessions."""
        now = datetime.now(tz=timezone.utc)

        full_session = BaseSession(
            session_id="full",
            timestamp=now,
            source="vermas",
            task_description="Full task",
            signals=[
                AgentSignal(
                    signal_id="s1",
                    agent_id="dev",
                    role="dev",
                    signal="done",
                    message="Done",
                    timestamp=now,
                    workflow_id="test",
                ),
            ],
            learnings=[AgentLearning(agent="dev", learnings=["Test"])],
            cycle_info=CycleInfo(mission_id="m", cycle=1, task_name="t"),
        )

        empty_session = BaseSession(
            session_id="empty",
            timestamp=now,
            source="vermas",
        )

        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_sessions([full_session, empty_session])
        # full: 4/4, empty: 0/4 => 4/8 = 50%
        assert result.value == 50.0
