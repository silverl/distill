"""Project notes formatter.

Aggregates sessions by project name and generates per-project
Obsidian markdown notes with timelines, milestones, and summaries.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from session_insights.formatters.templates import (
    format_duration,
    format_obsidian_link,
    format_tag,
)
from session_insights.parsers.models import BaseSession


def group_sessions_by_project(
    sessions: list[BaseSession],
) -> dict[str, list[BaseSession]]:
    """Group sessions by their project field.

    Sessions without a project are grouped under '(unassigned)'.

    Args:
        sessions: All sessions to group.

    Returns:
        Dict mapping project name to list of sessions, sorted by timestamp.
    """
    groups: dict[str, list[BaseSession]] = {}
    for session in sessions:
        key = session.project if session.project else "(unassigned)"
        groups.setdefault(key, []).append(session)
    # Sort each group by timestamp
    for key in groups:
        groups[key].sort(key=lambda s: s.timestamp)
    return groups


class ProjectFormatter:
    """Formatter for generating per-project Obsidian markdown notes."""

    def format_project_note(
        self, project_name: str, sessions: list[BaseSession]
    ) -> str:
        """Generate a project note aggregating all sessions for a project.

        Args:
            project_name: The project name.
            sessions: Sessions belonging to this project, sorted by timestamp.

        Returns:
            Obsidian-compatible markdown string.
        """
        frontmatter = self._format_frontmatter(project_name, sessions)
        body = self._format_body(project_name, sessions)
        return frontmatter + body

    @staticmethod
    def note_name(project_name: str) -> str:
        """Generate Obsidian-compatible note name for a project."""
        slug = project_name.replace(" ", "-").replace("/", "-").lower()
        return f"project-{slug}"

    def _format_frontmatter(
        self, project_name: str, sessions: list[BaseSession]
    ) -> str:
        """Generate YAML frontmatter for a project note."""
        total_duration = sum(s.duration_minutes or 0 for s in sessions)
        all_tags = {"project-note", "ai-session"}
        for s in sessions:
            all_tags.update(s.tags)
        tags_yaml = "\n".join(format_tag(t) for t in sorted(all_tags))

        # Date range
        timestamps = [s.timestamp for s in sessions if s.timestamp]
        first_date = min(timestamps).strftime("%Y-%m-%d") if timestamps else "unknown"
        last_date = max(timestamps).strftime("%Y-%m-%d") if timestamps else "unknown"

        lines = [
            "---",
            f"project: {project_name}",
            "type: project-note",
            f"total_sessions: {len(sessions)}",
            f"total_duration_minutes: {total_duration:.1f}",
            f"first_session: {first_date}",
            f"last_session: {last_date}",
            f"tags:",
            tags_yaml,
            f"created: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
            "---",
            "",
        ]
        return "\n".join(lines)

    def _format_body(
        self, project_name: str, sessions: list[BaseSession]
    ) -> str:
        """Generate the markdown body for a project note."""
        lines: list[str] = []

        # Title
        lines.append(f"# Project: {project_name}")
        lines.append("")

        # Overview
        lines.append("## Overview")
        lines.append("")
        total_duration = sum(s.duration_minutes or 0 for s in sessions)
        sources = Counter(s.source for s in sessions)
        sources_str = ", ".join(f"{src} ({cnt})" for src, cnt in sources.most_common())
        lines.append(f"- **Total Sessions:** {len(sessions)}")
        lines.append(f"- **Total Time:** {format_duration(total_duration)}")
        lines.append(f"- **Sources:** {sources_str}")
        if sessions:
            lines.append(
                f"- **Date Range:** {sessions[0].timestamp.strftime('%Y-%m-%d')} "
                f"to {sessions[-1].timestamp.strftime('%Y-%m-%d')}"
            )
        lines.append("")

        # Narrative summaries
        narratives = [s for s in sessions if s.narrative]
        if narratives:
            lines.append("## Project Narrative")
            lines.append("")
            # Show most recent narratives (up to 5)
            for s in narratives[-5:]:
                date_str = s.timestamp.strftime("%Y-%m-%d")
                lines.append(f"**{date_str}:** {s.narrative}")
                lines.append("")

        # Session timeline
        lines.append("## Session Timeline")
        lines.append("")
        lines.append("| Date | Time | Duration | Summary | Link |")
        lines.append("|------|------|----------|---------|------|")
        for s in sessions:
            date_str = s.timestamp.strftime("%Y-%m-%d")
            time_str = s.timestamp.strftime("%H:%M")
            dur_str = format_duration(s.duration_minutes)
            summary = s.summary[:60] + "..." if s.summary and len(s.summary) > 60 else (s.summary or "-")
            link = format_obsidian_link(s.note_name)
            lines.append(f"| {date_str} | {time_str} | {dur_str} | {summary} | {link} |")
        lines.append("")

        # Key outcomes
        all_outcomes = [o for s in sessions for o in s.outcomes]
        if all_outcomes:
            lines.append("## Key Outcomes")
            lines.append("")
            successes = [o for o in all_outcomes if o.success]
            failures = [o for o in all_outcomes if not o.success]
            lines.append(
                f"- **Completed:** {len(successes)} | **Incomplete:** {len(failures)}"
            )
            lines.append("")
            # List unique outcomes
            seen: set[str] = set()
            for o in all_outcomes:
                if o.description not in seen:
                    seen.add(o.description)
                    status = "done" if o.success else "pending"
                    lines.append(f"- [{status}] {o.description}")
            lines.append("")

        # Major Milestones (grouped by week)
        lines.append("## Major Milestones")
        lines.append("")
        weeks: dict[str, list[BaseSession]] = defaultdict(list)
        for s in sessions:
            week_key = s.timestamp.strftime("%Y-W%W")
            weeks[week_key].append(s)
        for week_key in sorted(weeks):
            week_sessions = weeks[week_key]
            date_range = (
                f"{week_sessions[0].timestamp.strftime('%Y-%m-%d')} - "
                f"{week_sessions[-1].timestamp.strftime('%Y-%m-%d')}"
            )
            lines.append(f"### {week_key} ({date_range})")
            lines.append("")
            for s in week_sessions:
                summary = s.summary or "Session"
                lines.append(f"- {summary}")
            lines.append("")

        # Key Decisions (extracted from session outcomes)
        lines.append("## Key Decisions")
        lines.append("")
        decisions = [
            o for s in sessions for o in s.outcomes if o.success
        ]
        if decisions:
            for d in decisions:
                lines.append(f"- {d.description}")
        else:
            lines.append("- No key decisions recorded")
        lines.append("")

        # Related Sessions (linked)
        lines.append("## Related Sessions")
        lines.append("")
        for s in sessions:
            date_str = s.timestamp.strftime("%Y-%m-%d %H:%M")
            link = format_obsidian_link(s.note_name, s.summary or s.note_name)
            lines.append(f"- {date_str}: {link}")
        lines.append("")

        # Files modified across all sessions
        all_files: Counter[str] = Counter()
        for s in sessions:
            for o in s.outcomes:
                for f in o.files_modified:
                    all_files[f] += 1
        if all_files:
            lines.append("## Files Modified")
            lines.append("")
            for filepath, count in all_files.most_common(20):
                lines.append(f"- `{filepath}` ({count}x)")
            lines.append("")

        # Tool usage across project
        tools: Counter[str] = Counter()
        for s in sessions:
            for t in s.tools_used:
                tools[t.name] += t.count
        if tools:
            lines.append("## Tool Usage")
            lines.append("")
            lines.append("| Tool | Total Calls |")
            lines.append("|------|-------------|")
            for tool_name, count in tools.most_common(10):
                lines.append(f"| {tool_name} | {count} |")
            lines.append("")

        # Tags summary
        all_tags: Counter[str] = Counter()
        for s in sessions:
            for tag in s.tags:
                all_tags[tag] += 1
        if all_tags:
            lines.append("## Activity Tags")
            lines.append("")
            tag_parts = [f"#{tag} ({cnt})" for tag, cnt in all_tags.most_common()]
            lines.append(" ".join(tag_parts))
            lines.append("")

        return "\n".join(lines)
