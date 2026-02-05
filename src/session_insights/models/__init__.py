"""Session data models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from session_insights.models.insight import (
    Insight,
    InsightCollection,
    InsightSeverity,
    InsightType,
)


class ToolUsage(BaseModel):
    """Represents a tool used during a session."""

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


class BaseSession(BaseModel):
    """Base model for AI coding assistant sessions."""

    id: str
    start_time: datetime
    end_time: datetime | None = None
    source: str = "unknown"  # 'claude-code', 'cursor', etc.
    summary: str = ""
    turns: list[ConversationTurn] = Field(default_factory=list)
    tools_used: list[ToolUsage] = Field(default_factory=list)
    outcomes: list[SessionOutcome] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_minutes(self) -> float | None:
        """Calculate session duration in minutes."""
        if self.end_time is None:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 60

    @property
    def note_name(self) -> str:
        """Generate Obsidian-compatible note name."""
        date_str = self.start_time.strftime("%Y-%m-%d")
        time_str = self.start_time.strftime("%H%M")
        return f"session-{date_str}-{time_str}-{self.id[:8]}"
