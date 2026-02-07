"""Obsidian-compatible markdown formatter."""

from collections import Counter
from datetime import date, datetime, timedelta

from distill.formatters.templates import (
    DAILY_BODY,
    DAILY_FRONTMATTER,
    SESSION_BODY,
    SESSION_FRONTMATTER,
    format_duration,
    format_obsidian_link,
    format_tag,
    format_yaml_list_item,
)
from distill.models import BaseSession


def _format_timedelta(td: timedelta) -> str:
    """Format a timedelta as a human-readable elapsed string."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    if minutes < 60:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if remaining_minutes:
        return f"{hours}h {remaining_minutes}m"
    return f"{hours}h"


class ObsidianFormatter:
    """Formatter for generating Obsidian-compatible markdown notes."""

    DEFAULT_TAGS = ["ai-session"]

    def __init__(self, include_conversation: bool = True) -> None:
        """Initialize the formatter.

        Args:
            include_conversation: Whether to include full conversation in output.
        """
        self.include_conversation = include_conversation

    def format_session(self, session: BaseSession) -> str:
        """Format a single session as an Obsidian markdown note.

        Args:
            session: The session to format.

        Returns:
            Obsidian-compatible markdown string with frontmatter.
        """
        frontmatter = self._format_session_frontmatter(session)
        body = self._format_session_body(session)
        return frontmatter + body

    def format_daily_summary(
        self, sessions: list[BaseSession], summary_date: date
    ) -> str:
        """Format a daily summary of multiple sessions.

        Args:
            sessions: List of sessions for the day.
            summary_date: The date to summarize.

        Returns:
            Obsidian-compatible markdown string with frontmatter.
        """
        frontmatter = self._format_daily_frontmatter(sessions, summary_date)
        body = self._format_daily_body(sessions, summary_date)
        return frontmatter + body

    def _format_session_frontmatter(self, session: BaseSession) -> str:
        """Generate YAML frontmatter for a session note."""
        # Collect all tags
        all_tags = list(self.DEFAULT_TAGS)
        all_tags.append(session.source)
        all_tags.extend(session.tags)
        tags_yaml = "\n".join(format_tag(tag) for tag in all_tags)

        # Collect tools
        tools = [t.name for t in session.tools_used]
        tools_yaml = "\n".join(format_yaml_list_item(tool) for tool in tools) if tools else "  []"

        # Calculate duration
        duration = session.duration_minutes
        duration_str = f"{duration:.1f}" if duration is not None else "null"

        return SESSION_FRONTMATTER.substitute(
            id=session.id,
            date=session.start_time.strftime("%Y-%m-%d"),
            time=session.start_time.strftime("%H:%M:%S"),
            source=session.source,
            duration=duration_str,
            tags=tags_yaml,
            tools=tools_yaml,
            created=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def _format_session_body(self, session: BaseSession) -> str:
        """Generate the markdown body for a session note."""
        # Title
        date_str = session.start_time.strftime("%Y-%m-%d %H:%M")
        title = f"Session {date_str}"

        # Summary
        summary = session.narrative if session.narrative else (
            session.summary if session.summary else "_No summary available._"
        )

        # Timeline
        start_time = session.start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_time = session.end_time.strftime("%Y-%m-%d %H:%M:%S") if session.end_time else "Ongoing"
        duration_str = format_duration(session.duration_minutes)

        # Tools section
        tools_section = self._format_tools_section(session)

        # Outcomes section
        outcomes_section = self._format_outcomes_section(session)

        # Conversation section
        conversation_section = self._format_conversation_section(session)

        # Related notes
        related_notes = self._format_related_notes(session)

        body = SESSION_BODY.substitute(
            title=title,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            duration_str=duration_str,
            tools_section=tools_section,
            outcomes_section=outcomes_section,
            conversation_section=conversation_section,
            related_notes=related_notes,
        )

        # Append source-specific sections
        if session.source == "vermas":
            body += self._format_vermas_sections(session)

        return body

    def _format_tools_section(self, session: BaseSession) -> str:
        """Format the tools used section."""
        if not session.tools_used:
            return "_No tools recorded._"

        lines = []
        for tool in session.tools_used:
            lines.append(f"- **{tool.name}**: {tool.count} call{'s' if tool.count > 1 else ''}")
        return "\n".join(lines)

    def _format_outcomes_section(self, session: BaseSession) -> str:
        """Format the outcomes section."""
        if not session.outcomes:
            return "_No outcomes recorded._"

        lines = []
        for outcome in session.outcomes:
            status = "done" if outcome.success else "incomplete"
            lines.append(f"- [{status}] {outcome.description}")
            if outcome.files_modified:
                for file in outcome.files_modified:
                    lines.append(f"  - Modified: `{file}`")
        return "\n".join(lines)

    def _format_conversation_section(self, session: BaseSession) -> str:
        """Format an enriched conversation section with structured subsections."""
        if not self.include_conversation:
            return "_Conversation not included._"

        parts = []

        # User Questions
        questions = self._extract_user_questions(session)
        if questions:
            parts.append("### User Questions\n")
            for i, q in enumerate(questions, 1):
                parts.append(f"{i}. {q}")
            parts.append("")

        # Tool Usage Analysis
        tool_analysis = self._format_tool_usage_analysis(session)
        if tool_analysis:
            parts.append("### Tool Usage\n")
            parts.append(tool_analysis)
            parts.append("")

        # Key Decisions
        decisions = self._extract_key_decisions(session)
        if decisions:
            parts.append("### Key Decisions\n")
            for d in decisions:
                parts.append(f"- {d}")
            parts.append("")

        # Accomplishments Summary
        accomplishments = self._format_accomplishments(session)
        if accomplishments:
            parts.append("### Accomplishments\n")
            parts.append(accomplishments)
            parts.append("")

        if not parts:
            return "_No conversation content available._"

        return "\n".join(parts)

    def _extract_user_questions(self, session: BaseSession) -> list[str]:
        """Extract user questions from conversation turns."""
        questions = []
        for turn in session.turns:
            if turn.role != "user":
                continue
            content = turn.content.strip()
            if not content:
                continue
            # Truncate long questions
            if len(content) > 200:
                content = content[:200] + "..."
            questions.append(content)
        return questions

    def _format_tool_usage_analysis(self, session: BaseSession) -> str:
        """Format tool usage with counts and context."""
        if not session.tools_used:
            return ""

        lines = []
        lines.append("| Tool | Calls | Context |")
        lines.append("|------|-------|---------|")

        # Build a map of tool -> arguments used for rationale
        tool_args: dict[str, list[str]] = {}
        for tc in session.tool_calls:
            args_list = tool_args.setdefault(tc.tool_name, [])
            # Extract key context from arguments
            for key in ("file_path", "command", "pattern", "query"):
                if key in tc.arguments:
                    val = str(tc.arguments[key])
                    if len(val) > 60:
                        val = val[:57] + "..."
                    args_list.append(val)

        for tool in session.tools_used:
            context_items = tool_args.get(tool.name, [])
            # Show up to 3 unique targets
            unique_targets = list(dict.fromkeys(context_items))[:3]
            context = ", ".join(f"`{t}`" for t in unique_targets) if unique_targets else "-"
            lines.append(f"| {tool.name} | {tool.count} | {context} |")

        return "\n".join(lines)

    def _extract_key_decisions(self, session: BaseSession) -> list[str]:
        """Extract key decisions from assistant turns."""
        decisions = []
        decision_markers = ["decided to", "chose to", "going to", "will ", "let me", "approach:"]

        for turn in session.turns:
            if turn.role != "assistant":
                continue
            content = turn.content.strip()
            if not content:
                continue
            # Look for sentences that contain decision indicators
            for sentence in content.replace("\n", " ").split(". "):
                sentence = sentence.strip()
                if not sentence:
                    continue
                lower = sentence.lower()
                if any(marker in lower for marker in decision_markers):
                    truncated = sentence[:150] + "..." if len(sentence) > 150 else sentence
                    # Ensure it ends cleanly
                    if not truncated.endswith((".", "...", "!", "?")):
                        truncated += "."
                    decisions.append(truncated)
                    if len(decisions) >= 10:
                        return decisions

        return decisions

    def _format_accomplishments(self, session: BaseSession) -> str:
        """Format accomplishments from session outcomes."""
        if not session.outcomes:
            return ""

        lines = []
        success_count = sum(1 for o in session.outcomes if o.success)
        total = len(session.outcomes)
        lines.append(f"**{success_count}/{total}** outcomes completed successfully.\n")

        for outcome in session.outcomes:
            icon = "done" if outcome.success else "pending"
            lines.append(f"- [{icon}] {outcome.description}")
            if outcome.files_modified:
                files_str = ", ".join(f"`{f}`" for f in outcome.files_modified)
                lines.append(f"  - Files: {files_str}")

        return "\n".join(lines)

    def _format_related_notes(self, session: BaseSession) -> str:
        """Format related notes section with Obsidian links."""
        # Link to daily summary
        date_str = session.start_time.strftime("%Y-%m-%d")
        daily_link = format_obsidian_link(f"daily-{date_str}", f"Daily Summary {date_str}")
        return f"- {daily_link}"

    def _format_daily_frontmatter(
        self, sessions: list[BaseSession], summary_date: date
    ) -> str:
        """Generate YAML frontmatter for a daily summary."""
        total_duration = sum(
            s.duration_minutes or 0 for s in sessions
        )

        # Collect all tags
        all_tags = ["daily-summary", "ai-session"]
        sources = {s.source for s in sessions}
        all_tags.extend(sources)
        tags_yaml = "\n".join(format_tag(tag) for tag in all_tags)

        return DAILY_FRONTMATTER.substitute(
            date=summary_date.isoformat(),
            total_sessions=len(sessions),
            total_duration=f"{total_duration:.1f}",
            tags=tags_yaml,
            created=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def _format_daily_body(
        self, sessions: list[BaseSession], summary_date: date
    ) -> str:
        """Generate the markdown body for a daily summary."""
        total_duration = sum(s.duration_minutes or 0 for s in sessions)

        # Collect unique tools
        all_tools: Counter[str] = Counter()
        for session in sessions:
            for tool in session.tools_used:
                all_tools[tool.name] += tool.count

        # Sessions list
        sessions_list = self._format_sessions_list(sessions)

        # Tool stats
        tool_stats = self._format_tool_stats(all_tools)

        # Patterns
        patterns_section = self._format_patterns(sessions)

        return DAILY_BODY.substitute(
            date=summary_date.isoformat(),
            total_sessions=len(sessions),
            total_duration_str=format_duration(total_duration),
            unique_tools_count=len(all_tools),
            sessions_list=sessions_list,
            tool_stats=tool_stats,
            patterns_section=patterns_section,
            notes_section="_Add your notes here._",
        )

    def _format_sessions_list(self, sessions: list[BaseSession]) -> str:
        """Format the list of sessions for daily summary."""
        if not sessions:
            return "_No sessions recorded._"

        lines = []
        for session in sorted(sessions, key=lambda s: s.start_time):
            link = format_obsidian_link(session.note_name)
            time_str = session.start_time.strftime("%H:%M")
            duration = format_duration(session.duration_minutes)
            text = session.narrative or session.summary or ""
            summary = text[:50] + "..." if len(text) > 50 else text
            summary = summary if summary else "No summary"
            lines.append(f"- {time_str} - {link}: {summary} ({duration})")
        return "\n".join(lines)

    def _format_tool_stats(self, tools: Counter[str]) -> str:
        """Format tool usage statistics."""
        if not tools:
            return "_No tools used._"

        lines = []
        for tool, count in tools.most_common():
            lines.append(f"| {tool} | {count} |")

        header = "| Tool | Count |\n|------|-------|"
        return header + "\n" + "\n".join(lines)

    def _format_patterns(self, sessions: list[BaseSession]) -> str:
        """Format observed patterns from sessions."""
        if not sessions:
            return "_No patterns detected._"

        patterns = []

        # Average session duration
        durations = [s.duration_minutes for s in sessions if s.duration_minutes]
        if durations:
            avg_duration = sum(durations) / len(durations)
            patterns.append(f"- Average session length: {format_duration(avg_duration)}")

        # Most common tools
        all_tools: Counter[str] = Counter()
        for session in sessions:
            for tool in session.tools_used:
                all_tools[tool.name] += tool.count

        if all_tools:
            top_tools = all_tools.most_common(3)
            tools_str = ", ".join(f"{t[0]} ({t[1]})" for t in top_tools)
            patterns.append(f"- Most used tools: {tools_str}")

        # Success rate
        all_outcomes = [o for s in sessions for o in s.outcomes]
        if all_outcomes:
            success_count = sum(1 for o in all_outcomes if o.success)
            rate = (success_count / len(all_outcomes)) * 100
            patterns.append(f"- Outcome success rate: {rate:.0f}%")

        return "\n".join(patterns) if patterns else "_No patterns detected._"

    # --- VerMAS-specific sections ---

    def _format_vermas_sections(self, session: BaseSession) -> str:
        """Format VerMAS-specific sections (task, signals, quality, learnings)."""
        sections = []

        task_section = self._format_vermas_task_section(session)
        if task_section:
            sections.append(task_section)

        signals_section = self._format_vermas_signals_section(session)
        if signals_section:
            sections.append(signals_section)

        quality_section = self._format_vermas_quality_section(session)
        if quality_section:
            sections.append(quality_section)

        learnings_section = self._format_vermas_learnings_section(session)
        if learnings_section:
            sections.append(learnings_section)

        return "\n" + "\n".join(sections) if sections else ""

    def _format_vermas_task_section(self, session: BaseSession) -> str:
        """Format VerMAS task details section."""
        lines = ["## Task Details", ""]

        cycle_info = session.cycle_info
        task_name = cycle_info.task_name if cycle_info else None
        mission_id = cycle_info.mission_id if cycle_info else None
        cycle = cycle_info.cycle if cycle_info else None
        outcome = cycle_info.outcome if cycle_info else "unknown"

        if task_name:
            lines.append(f"- **Task:** {task_name}")
        if mission_id:
            lines.append(f"- **Mission:** {mission_id}")
        if cycle is not None:
            lines.append(f"- **Cycle:** {cycle}")
        lines.append(f"- **Outcome:** {outcome}")
        if session.quality_rating:
            lines.append(f"- **Quality:** {session.quality_rating}")

        if session.task_description:
            lines.append("")
            lines.append("### Description")
            lines.append("")
            lines.append(session.task_description)

        lines.append("")
        return "\n".join(lines)

    def _format_vermas_signals_section(self, session: BaseSession) -> str:
        """Format VerMAS agent signals timeline with elapsed durations."""
        signals = session.signals
        if not signals:
            return ""

        sorted_signals = sorted(signals, key=lambda s: s.timestamp)

        lines = ["## Agent Signals", ""]
        lines.append("| Time | Elapsed | Agent | Role | Signal | Message |")
        lines.append("|------|---------|-------|------|--------|---------|")

        first_ts = sorted_signals[0].timestamp
        prev_ts = first_ts
        for signal in sorted_signals:
            time_str = signal.timestamp.strftime("%H:%M:%S")
            elapsed = signal.timestamp - first_ts
            elapsed_str = _format_timedelta(elapsed)
            msg = signal.message[:60] + "..." if len(signal.message) > 60 else signal.message
            lines.append(
                f"| {time_str} | {elapsed_str} | {signal.agent_id[:12]} | {signal.role} "
                f"| {signal.signal} | {msg} |"
            )
            prev_ts = signal.timestamp

        # Total workflow duration
        if len(sorted_signals) >= 2:
            total = sorted_signals[-1].timestamp - sorted_signals[0].timestamp
            lines.append("")
            lines.append(f"**Total workflow time:** {_format_timedelta(total)}")

        lines.append("")
        return "\n".join(lines)

    def _format_vermas_quality_section(self, session: BaseSession) -> str:
        """Format VerMAS quality assessment section."""
        qa = session.quality_assessment
        if qa is None:
            return ""

        lines = ["## Quality Assessment", ""]

        if qa.score is not None:
            # Display score as a rating out of 100
            pct = qa.score * 100
            lines.append(f"**Overall Score:** {pct:.0f}/100\n")

        if qa.criteria:
            lines.append("| Criterion | Score |")
            lines.append("|-----------|-------|")
            for criterion, score in qa.criteria.items():
                display_name = criterion.replace("_", " ").title()
                lines.append(f"| {display_name} | {score * 100:.0f}/100 |")
            lines.append("")

        if qa.notes:
            lines.append(f"**Notes:** {qa.notes}")
            lines.append("")

        return "\n".join(lines)

    def _format_vermas_learnings_section(self, session: BaseSession) -> str:
        """Format VerMAS agent learnings and improvements."""
        agent_learnings = session.learnings
        improvements = session.improvements

        if not agent_learnings and not improvements:
            return ""

        lines = ["## Learnings", ""]

        for learning in agent_learnings:
            lines.append(f"### Agent: {learning.agent}")
            if learning.learnings:
                for item in learning.learnings:
                    lines.append(f"- {item}")
            if learning.best_practices:
                lines.append("")
                lines.append("**Best Practices:**")
                for item in learning.best_practices:
                    lines.append(f"- {item}")
            lines.append("")

        if improvements:
            lines.append("### Improvements")
            lines.append("")
            for imp in improvements:
                status = "validated" if imp.validated else "pending"
                lines.append(f"- **{imp.type}** ({imp.target}): {imp.change} [{status}]")
                if imp.impact:
                    lines.append(f"  - Impact: {imp.impact}")
            lines.append("")

        return "\n".join(lines)
