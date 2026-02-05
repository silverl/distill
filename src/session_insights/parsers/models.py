"""Unified session data models.

This module defines the single BaseSession model used by both parsers and formatters.
Parsers populate raw data (messages, tool_calls), and enriched fields (turns, tools_used,
outcomes) are either auto-derived or set directly.

All shared model types live here to avoid circular imports between parsers and formatters.
"""

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    """Represents a message in a conversation."""

    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime | None = None


class ToolCall(BaseModel):
    """Represents an individual tool call made during a session."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    duration_ms: int | None = None


# Backward compatibility alias for parsers that import ToolUsage
ToolUsage = ToolCall


class ToolUsageSummary(BaseModel):
    """Aggregated tool usage summary for display."""

    name: str
    count: int = 1
    arguments: list[dict[str, Any]] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    """Represents a single turn in the conversation."""

    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime | None = None
    tools_called: list[str] = Field(default_factory=list)


class SessionOutcome(BaseModel):
    """Represents an outcome or result of a session."""

    description: str
    files_modified: list[str] = Field(default_factory=list)
    success: bool = True


class AgentSignal(BaseModel):
    """Represents a signal sent by an agent in a workflow."""

    signal_id: str
    agent_id: str
    role: str
    signal: str  # done, approved, needs_revision, blocked, complete, progress
    message: str
    timestamp: datetime
    workflow_id: str
    metadata: dict[str, Any] | None = None


class AgentLearning(BaseModel):
    """Represents agent learnings from knowledge files."""

    agent: str = "general"
    learnings: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    best_practices: list[str] = Field(default_factory=list)


class KnowledgeImprovement(BaseModel):
    """Represents an adaptation/improvement record from knowledge files."""

    id: str
    date: datetime | None = None
    type: str = ""
    target: str = ""
    change: str = ""
    before_metrics: dict[str, Any] = Field(default_factory=dict)
    after_metrics: dict[str, Any] = Field(default_factory=dict)
    validated: bool = False
    impact: str = ""


class CycleInfo(BaseModel):
    """Workflow cycle metadata."""

    mission_id: str | None = None
    cycle: int | None = None
    workflow_id: str | None = None
    task_name: str | None = None
    outcome: str = "unknown"


class QualityAssessment(BaseModel):
    """Quality assessment of a session's work."""

    score: float | None = None
    criteria: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class BaseSession(BaseModel):
    """Unified base model for AI coding assistant sessions.

    Accepts construction with either parser fields (session_id, timestamp,
    messages, tool_calls) or formatter fields (id, start_time, turns,
    tools_used, outcomes). Auto-derives enriched fields from raw data
    when not directly provided.
    """

    # Core identity
    session_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.min)

    # Time range
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Source and description
    source: str = "unknown"
    summary: str = ""

    # Raw parser data
    messages: list[Message] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    # Enriched/formatted data
    turns: list[ConversationTurn] = Field(default_factory=list)
    tools_used: list[ToolUsageSummary] = Field(default_factory=list)
    outcomes: list[SessionOutcome] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Task and workflow context
    task_description: str = ""
    signals: list[AgentSignal] = Field(default_factory=list)
    learnings: list[AgentLearning] = Field(default_factory=list)
    improvements: list[KnowledgeImprovement] = Field(default_factory=list)
    quality_assessment: QualityAssessment | None = None
    cycle_info: CycleInfo | None = None

    # Extra
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        """Accept both parser and formatter field names."""
        if isinstance(data, dict):
            # Accept 'id' as alias for 'session_id'
            if "id" in data and not data.get("session_id"):
                data["session_id"] = data.pop("id")
            elif "id" in data:
                data.pop("id")

            # Sync start_time and timestamp
            if "start_time" in data and not data.get("timestamp"):
                data["timestamp"] = data["start_time"]
            elif "timestamp" in data and "start_time" not in data:
                data["start_time"] = data["timestamp"]
        return data

    @staticmethod
    def _ensure_utc(dt: datetime | None) -> datetime | None:
        """Normalize a datetime to UTC-aware. Returns None if input is None."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def model_post_init(self, __context: Any) -> None:
        """Auto-derive enriched fields from raw data if not directly provided."""
        # Normalize all datetimes to UTC-aware to prevent comparison errors
        self.timestamp = self._ensure_utc(self.timestamp) or datetime.min.replace(
            tzinfo=timezone.utc
        )
        self.start_time = self._ensure_utc(self.start_time)
        self.end_time = self._ensure_utc(self.end_time)

        # Derive tools_used from tool_calls
        if not self.tools_used and self.tool_calls:
            tool_counts: Counter[str] = Counter(
                tc.tool_name for tc in self.tool_calls
            )
            self.tools_used = [
                ToolUsageSummary(name=name, count=count)
                for name, count in tool_counts.items()
            ]

        # Derive turns from messages
        if not self.turns and self.messages:
            self.turns = [
                ConversationTurn(
                    role=m.role, content=m.content, timestamp=m.timestamp
                )
                for m in self.messages
            ]

    @property
    def id(self) -> str:
        """Alias for session_id (backward compatibility)."""
        return self.session_id

    @property
    def note_name(self) -> str:
        """Generate Obsidian-compatible note name."""
        ts = self.start_time or self.timestamp
        date_str = ts.strftime("%Y-%m-%d")
        time_str = ts.strftime("%H%M")
        return f"session-{date_str}-{time_str}-{self.session_id[:8]}"

    @property
    def duration_minutes(self) -> float | None:
        """Calculate session duration in minutes."""
        st = self.start_time or self.timestamp
        et = self.end_time
        if et is None:
            # Fall back to deriving from message timestamps (need 2+ for a span)
            timestamps = [
                self._ensure_utc(m.timestamp)
                for m in self.messages
                if m.timestamp is not None
            ]
            if len(timestamps) >= 2:
                et = max(timestamps)
        if et is None:
            return None
        delta = et - st
        return delta.total_seconds() / 60
