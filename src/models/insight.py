"""Insight models for pattern analysis."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InsightType(str, Enum):
    """Types of insights that can be generated."""

    SUCCESS_PATTERN = "success_pattern"
    FAILURE_PATTERN = "failure_pattern"
    TIMELINE_PATTERN = "timeline_pattern"
    CROSS_SESSION_CORRELATION = "cross_session_correlation"
    TOOL_USAGE_PATTERN = "tool_usage_pattern"
    PRODUCTIVITY_INSIGHT = "productivity_insight"


class InsightSeverity(str, Enum):
    """Severity/importance level of an insight."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Insight(BaseModel):
    """Represents an insight derived from session analysis.

    Insights are observations, patterns, or recommendations generated
    by analyzing session data. They help users understand their
    coding practices and identify areas for improvement.
    """

    id: str
    type: InsightType
    title: str
    description: str
    severity: InsightSeverity = InsightSeverity.MEDIUM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.now)
    session_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Generate a short summary of the insight."""
        return f"[{self.severity.value.upper()}] {self.title}"


class InsightCollection(BaseModel):
    """Collection of insights from analysis."""

    insights: list[Insight] = Field(default_factory=list)
    analysis_timestamp: datetime = Field(default_factory=datetime.now)
    sessions_analyzed: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def filter_by_type(self, insight_type: InsightType) -> list[Insight]:
        """Filter insights by type."""
        return [i for i in self.insights if i.type == insight_type]

    def filter_by_severity(self, severity: InsightSeverity) -> list[Insight]:
        """Filter insights by severity."""
        return [i for i in self.insights if i.severity == severity]

    @property
    def high_priority(self) -> list[Insight]:
        """Get high-priority insights."""
        return self.filter_by_severity(InsightSeverity.HIGH)
