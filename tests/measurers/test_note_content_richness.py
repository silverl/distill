"""Tests for note_content_richness KPI measurer."""

import json
from datetime import datetime, timezone

import pytest

from session_insights.measurers.base import KPIResult
from session_insights.measurers.note_content_richness import (
    NoteContentRichnessMeasurer,
    _score_note,
)
from session_insights.parsers.models import (
    AgentLearning,
    AgentSignal,
    BaseSession,
    CycleInfo,
    Message,
    SessionOutcome,
    ToolCall,
)


class TestScoreNote:
    """Tests for the note scoring function."""

    def test_score_empty_note(self) -> None:
        """Empty note should have all fields false."""
        scores = _score_note("", "claude")
        assert all(not v for v in scores.values())

    def test_score_rich_claude_note(self) -> None:
        """Note with all expected fields should score all true."""
        content = """---
start_time: 2024-01-15
duration: 30min
---
# Session

## Tools
- Read: 5 calls

## Outcomes
- Fixed bug

## Conversation
> User: help
"""
        scores = _score_note(content, "claude")
        assert scores["has_timestamps"]
        assert scores["has_duration"]
        assert scores["has_tool_list"]
        assert scores["has_outcomes"]
        assert scores["has_conversation_summary"]

    def test_score_vermas_note(self) -> None:
        """VerMAS note should check for vermas-specific fields."""
        content = """---
start_time: 2024-01-15
duration: 15min
---
# Session

## Tools
- Bash: 3 calls

## Outcomes
- Task completed

## Task Details
- Task: implement-feature

## Agent Signals
| Time | Agent | Role | Signal |

## Learnings
### Agent: general
"""
        scores = _score_note(content, "vermas")
        assert scores["has_timestamps"]
        assert scores["has_duration"]
        assert scores["has_tool_list"]
        assert scores["has_outcomes"]
        assert scores["has_vermas_task_details"]
        assert scores["has_vermas_signals"]
        assert scores["has_vermas_learnings"]

    def test_score_partial_note(self) -> None:
        """Partially complete note should have mixed scores."""
        content = """---
start_time: 2024-01-15
---
# Session

## Outcomes
- Done
"""
        scores = _score_note(content, "claude")
        assert scores["has_timestamps"]
        assert not scores["has_duration"]
        assert not scores["has_tool_list"]
        assert scores["has_outcomes"]


class TestNoteContentRichnessMeasurer:
    """Tests for the note_content_richness measurer."""

    def test_result_is_kpi_result(self) -> None:
        """Measurer returns a KPIResult."""
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure()
        assert isinstance(result, KPIResult)
        assert result.kpi == "note_content_richness"
        assert result.target == 90.0

    def test_value_in_range(self) -> None:
        """Measured value is between 0 and 100."""
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure()
        assert 0.0 <= result.value <= 100.0

    def test_details_contain_note_info(self) -> None:
        """Details include per-note scores."""
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure()
        assert "total_notes" in result.details
        assert "per_note" in result.details

    def test_json_serialization(self) -> None:
        """Result serializes to valid JSON."""
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure()
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["kpi"] == "note_content_richness"

    def test_measure_from_sessions_empty(self) -> None:
        """Empty session list gives 0% value."""
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure_from_sessions([])
        assert result.value == 0.0
        assert "error" in result.details

    def test_measure_from_rich_session(self) -> None:
        """Session with all fields should score well."""
        now = datetime.now(tz=timezone.utc)
        session = BaseSession(
            session_id="rich-001",
            timestamp=now,
            source="claude",
            summary="Fixed auth bug",
            start_time=now,
            messages=[
                Message(role="user", content="Help", timestamp=now),
                Message(role="assistant", content="Sure", timestamp=now),
            ],
            tool_calls=[
                ToolCall(tool_name="Read"),
                ToolCall(tool_name="Edit"),
            ],
            outcomes=[
                SessionOutcome(description="Bug fixed", success=True),
            ],
        )
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure_from_sessions([session])
        assert result.value > 0.0
        assert result.details["total_notes"] == 1

    def test_measure_from_vermas_session(self) -> None:
        """VerMAS session with metadata should score well."""
        now = datetime.now(tz=timezone.utc)
        session = BaseSession(
            session_id="vermas-001",
            timestamp=now,
            source="vermas",
            summary="Workflow complete",
            start_time=now,
            task_description="Implement new feature",
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
                AgentLearning(
                    agent="general",
                    learnings=["Tests help"],
                ),
            ],
            cycle_info=CycleInfo(
                mission_id="test",
                cycle=1,
                task_name="feature",
            ),
            tool_calls=[ToolCall(tool_name="Bash")],
            outcomes=[SessionOutcome(description="Task done", success=True)],
        )
        measurer = NoteContentRichnessMeasurer()
        result = measurer.measure_from_sessions([session])
        assert result.value > 0.0
        # Check vermas-specific fields are in the per-note scores
        per_note = result.details["per_note"]
        assert len(per_note) == 1
        scores = per_note[0]["scores"]
        assert "has_vermas_task_details" in scores
