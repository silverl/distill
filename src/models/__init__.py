"""Session data models.

Re-exports unified models from parsers.models. The BaseSession class is the single
source of truth, accepting both parser fields (session_id, timestamp) and formatter
fields (id, start_time).
"""

from distill.models.insight import (
    Insight,
    InsightCollection,
    InsightSeverity,
    InsightType,
)
from distill.parsers.models import (
    AgentLearning,
    AgentSignal,
    BaseSession,
    ConversationTurn,
    CycleInfo,
    KnowledgeImprovement,
    QualityAssessment,
    SessionOutcome,
    ToolUsageSummary,
)

# Backward compatibility: formatter tests import ToolUsage from models
# This is the aggregated summary type (name, count), NOT the per-invocation ToolCall
ToolUsage = ToolUsageSummary

__all__ = [
    "AgentLearning",
    "AgentSignal",
    "BaseSession",
    "ConversationTurn",
    "CycleInfo",
    "Insight",
    "InsightCollection",
    "InsightSeverity",
    "InsightType",
    "KnowledgeImprovement",
    "QualityAssessment",
    "SessionOutcome",
    "ToolUsage",
    "ToolUsageSummary",
]
