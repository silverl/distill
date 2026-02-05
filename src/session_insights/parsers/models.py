"""Parser-specific models for session data."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Represents a message in a conversation."""

    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime | None = None


class ToolUsage(BaseModel):
    """Represents a tool call made during a session."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    duration_ms: int | None = None


class BaseSession(BaseModel):
    """Abstract base model for AI coding assistant sessions.

    This serves as the common interface for sessions from different sources
    (Claude, Cursor, etc.).
    """

    session_id: str
    timestamp: datetime
    source: str = "unknown"
    messages: list[Message] = Field(default_factory=list)
    tool_calls: list[ToolUsage] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_minutes(self) -> float | None:
        """Calculate session duration based on first and last message timestamps."""
        timestamps = [m.timestamp for m in self.messages if m.timestamp is not None]
        if len(timestamps) < 2:
            return None
        delta = max(timestamps) - min(timestamps)
        return delta.total_seconds() / 60
