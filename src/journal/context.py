"""Session-to-context compression for LLM synthesis (Phase 1).

Transforms a list of BaseSession objects for a single day into a compact,
structured DailyContext suitable for sending to an LLM. This module is
fully deterministic and testable without any LLM calls.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from distill.journal.config import JournalConfig
from distill.parsers.models import BaseSession


class SessionSummaryForLLM(BaseModel):
    """Compact session summary optimized for LLM context."""

    time: str
    duration_minutes: float | None = None
    source: str = "unknown"
    project: str = ""
    summary: str = ""
    narrative: str = ""
    outcomes: list[str] = Field(default_factory=list)
    top_tools: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    cycle_outcome: str | None = None


class DailyContext(BaseModel):
    """Compressed context for a single day's sessions."""

    date: date
    total_sessions: int
    total_duration_minutes: float
    projects_worked: list[str] = Field(default_factory=list)
    session_summaries: list[SessionSummaryForLLM] = Field(default_factory=list)
    key_outcomes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    previous_context: str = ""

    def render_text(self) -> str:
        """Render as structured text for LLM context."""
        lines: list[str] = []
        lines.append(f"# Daily Session Context: {self.date.isoformat()}")
        lines.append("")
        lines.append(f"Sessions: {self.total_sessions}")
        lines.append(f"Total time: {self.total_duration_minutes:.0f} minutes")
        if self.projects_worked:
            lines.append(f"Projects: {', '.join(self.projects_worked)}")
        lines.append("")

        for i, s in enumerate(self.session_summaries, 1):
            lines.append(f"## Session {i} ({s.time}, {s.source})")
            if s.project:
                lines.append(f"Project: {s.project}")
            if s.duration_minutes is not None:
                lines.append(f"Duration: {s.duration_minutes:.0f}min")
            if s.summary:
                lines.append(f"Summary: {s.summary}")
            if s.narrative:
                lines.append(f"Narrative: {s.narrative}")
            if s.outcomes:
                lines.append("Outcomes:")
                for outcome in s.outcomes:
                    lines.append(f"  - {outcome}")
            if s.top_tools:
                lines.append(f"Tools: {', '.join(s.top_tools)}")
            if s.user_questions:
                lines.append("User questions:")
                for q in s.user_questions:
                    lines.append(f"  - {q}")
            if s.tags:
                lines.append(f"Tags: {', '.join(s.tags)}")
            if s.cycle_outcome:
                lines.append(f"Workflow outcome: {s.cycle_outcome}")
            lines.append("")

        if self.key_outcomes:
            lines.append("## Key Outcomes")
            for outcome in self.key_outcomes:
                lines.append(f"- {outcome}")
            lines.append("")

        if self.tags:
            lines.append(f"Tags across sessions: {', '.join(self.tags)}")

        if self.previous_context:
            lines.append("")
            lines.append(self.previous_context)

        return "\n".join(lines)


def _extract_session_summary(session: BaseSession) -> SessionSummaryForLLM:
    """Extract a compact summary from a single session."""
    # Top 3 tools by usage count
    top_tools = sorted(session.tools_used, key=lambda t: t.count, reverse=True)[:3]

    # User questions from conversation turns
    user_questions = [
        turn.content[:200]
        for turn in session.turns
        if turn.role == "user" and turn.content.strip()
    ][:5]

    # Outcomes as strings
    outcomes = [o.description for o in session.outcomes if o.description]

    # Cycle outcome for VerMAS sessions
    cycle_outcome = None
    if session.cycle_info:
        cycle_outcome = session.cycle_info.outcome

    return SessionSummaryForLLM(
        time=session.start_time.strftime("%H:%M"),
        duration_minutes=session.duration_minutes,
        source=session.source,
        project=session.project,
        summary=session.summary[:300] if session.summary else "",
        narrative=session.narrative[:300] if session.narrative else "",
        outcomes=outcomes[:5],
        top_tools=[t.name for t in top_tools],
        tags=session.tags[:10],
        user_questions=user_questions,
        cycle_outcome=cycle_outcome,
    )


def prepare_daily_context(
    sessions: list[BaseSession],
    target_date: date,
    config: JournalConfig,
) -> DailyContext:
    """Compress a day's sessions into LLM-ready context.

    Args:
        sessions: All sessions (will be filtered to target_date).
        target_date: The date to generate context for.
        config: Journal configuration.

    Returns:
        DailyContext with compressed session data.
    """
    # Filter to target date
    day_sessions = [
        s for s in sessions if s.start_time.date() == target_date
    ]

    # Sort by start time
    day_sessions.sort(key=lambda s: s.start_time)

    # Limit sessions
    day_sessions = day_sessions[: config.max_sessions_per_entry]

    # Aggregate data
    total_duration = sum(s.duration_minutes or 0 for s in day_sessions)

    projects = list(dict.fromkeys(
        s.project for s in day_sessions if s.project and s.project not in ("(unknown)", "(unassigned)")
    ))

    all_outcomes: list[str] = []
    all_tags: list[str] = []
    summaries: list[SessionSummaryForLLM] = []

    for session in day_sessions:
        summaries.append(_extract_session_summary(session))
        for outcome in session.outcomes:
            if outcome.description and outcome.description not in all_outcomes:
                all_outcomes.append(outcome.description)
        for tag in session.tags:
            if tag not in all_tags:
                all_tags.append(tag)

    return DailyContext(
        date=target_date,
        total_sessions=len(day_sessions),
        total_duration_minutes=total_duration,
        projects_worked=projects,
        session_summaries=summaries,
        key_outcomes=all_outcomes[:15],
        tags=all_tags[:20],
    )
