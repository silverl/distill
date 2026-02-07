"""Weekly digest formatter.

Groups sessions by ISO week and generates weekly summary markdown
with accomplishments, project breakdown, and tool statistics.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from distill.formatters.templates import (
    format_duration,
    format_obsidian_link,
    format_tag,
)
from distill.parsers.models import BaseSession


def group_sessions_by_week(
    sessions: list[BaseSession],
) -> dict[tuple[int, int], list[BaseSession]]:
    """Group sessions by ISO year and week number.

    Args:
        sessions: All sessions to group.

    Returns:
        Dict mapping (iso_year, iso_week) to list of sessions, sorted by timestamp.
    """
    groups: dict[tuple[int, int], list[BaseSession]] = {}
    for session in sessions:
        iso_cal = session.timestamp.isocalendar()
        key = (iso_cal[0], iso_cal[1])
        groups.setdefault(key, []).append(session)
    for key in groups:
        groups[key].sort(key=lambda s: s.timestamp)
    return groups


def week_start_date(iso_year: int, iso_week: int) -> date:
    """Get the Monday date for a given ISO year and week."""
    jan4 = date(iso_year, 1, 4)
    start = jan4 - timedelta(days=jan4.weekday())
    return start + timedelta(weeks=iso_week - 1)


class WeeklyDigestFormatter:
    """Formatter for generating weekly digest Obsidian markdown notes."""

    def format_weekly_digest(
        self,
        iso_year: int,
        iso_week: int,
        sessions: list[BaseSession],
    ) -> str:
        """Generate a weekly digest note.

        Args:
            iso_year: ISO year number.
            iso_week: ISO week number.
            sessions: Sessions for this week, sorted by timestamp.

        Returns:
            Obsidian-compatible markdown string.
        """
        frontmatter = self._format_frontmatter(iso_year, iso_week, sessions)
        body = self._format_body(iso_year, iso_week, sessions)
        return frontmatter + body

    @staticmethod
    def note_name(iso_year: int, iso_week: int) -> str:
        """Generate Obsidian-compatible note name for a weekly digest."""
        return f"weekly-{iso_year}-W{iso_week:02d}"

    def _format_frontmatter(
        self, iso_year: int, iso_week: int, sessions: list[BaseSession]
    ) -> str:
        """Generate YAML frontmatter for a weekly digest."""
        total_duration = sum(s.duration_minutes or 0 for s in sessions)
        monday = week_start_date(iso_year, iso_week)
        sunday = monday + timedelta(days=6)

        all_tags = {"weekly-digest", "ai-session"}
        for s in sessions:
            all_tags.update(s.tags)
        tags_yaml = "\n".join(format_tag(t) for t in sorted(all_tags))

        lines = [
            "---",
            "type: weekly-digest",
            f"week: {iso_year}-W{iso_week:02d}",
            f"week_start: {monday.isoformat()}",
            f"week_end: {sunday.isoformat()}",
            f"total_sessions: {len(sessions)}",
            f"total_duration_minutes: {total_duration:.1f}",
            f"tags:",
            tags_yaml,
            f"created: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
            "---",
            "",
        ]
        return "\n".join(lines)

    def _format_body(
        self, iso_year: int, iso_week: int, sessions: list[BaseSession]
    ) -> str:
        """Generate the markdown body for a weekly digest."""
        monday = week_start_date(iso_year, iso_week)
        sunday = monday + timedelta(days=6)
        lines: list[str] = []

        # Title
        lines.append(
            f"# Weekly Digest: {iso_year}-W{iso_week:02d} "
            f"({monday.isoformat()} to {sunday.isoformat()})"
        )
        lines.append("")

        # Overview
        total_duration = sum(s.duration_minutes or 0 for s in sessions)
        projects = set(s.project for s in sessions if s.project)
        lines.append("## Overview")
        lines.append("")
        lines.append(f"- **Sessions:** {len(sessions)}")
        lines.append(f"- **Total Time:** {format_duration(total_duration)}")
        lines.append(f"- **Projects:** {len(projects)}")
        days_active = len(set(s.timestamp.date() for s in sessions))
        lines.append(f"- **Days Active:** {days_active}/7")
        lines.append("")

        # Accomplishments from narratives
        narratives = [s for s in sessions if s.narrative]
        if narratives:
            lines.append("## Accomplishments")
            lines.append("")
            for s in narratives:
                date_str = s.timestamp.strftime("%Y-%m-%d")
                project_prefix = f"[{s.project}] " if s.project else ""
                lines.append(f"- **{date_str}** {project_prefix}{s.narrative}")
            lines.append("")

        # Projects breakdown
        if projects:
            lines.append("## Projects")
            lines.append("")
            project_groups: dict[str, list[BaseSession]] = {}
            for s in sessions:
                key = s.project if s.project else "(unassigned)"
                project_groups.setdefault(key, []).append(s)

            for proj_name, proj_sessions in sorted(
                project_groups.items(), key=lambda x: -len(x[1])
            ):
                proj_duration = sum(s.duration_minutes or 0 for s in proj_sessions)
                proj_link = format_obsidian_link(
                    f"projects/project-{proj_name.lower().replace(' ', '-')}",
                    proj_name,
                )
                lines.append(
                    f"### {proj_link} ({len(proj_sessions)} sessions, "
                    f"{format_duration(proj_duration)})"
                )
                lines.append("")
                for s in proj_sessions:
                    time_str = s.timestamp.strftime("%Y-%m-%d %H:%M")
                    summary = s.summary[:50] + "..." if s.summary and len(s.summary) > 50 else (s.summary or "-")
                    link = format_obsidian_link(s.note_name)
                    lines.append(f"- {time_str} {link}: {summary}")
                lines.append("")

        # Daily breakdown
        daily_groups: dict[date, list[BaseSession]] = {}
        for s in sessions:
            d = s.timestamp.date()
            daily_groups.setdefault(d, []).append(s)

        lines.append("## Daily Breakdown")
        lines.append("")
        lines.append("| Day | Sessions | Duration | Top Activity |")
        lines.append("|-----|----------|----------|-------------|")
        for d in sorted(daily_groups.keys()):
            day_sessions = daily_groups[d]
            day_dur = sum(s.duration_minutes or 0 for s in day_sessions)
            # Find top tag for the day
            day_tags: Counter[str] = Counter()
            for s in day_sessions:
                for tag in s.tags:
                    day_tags[tag] += 1
            top_tag = day_tags.most_common(1)[0][0] if day_tags else "-"
            day_link = format_obsidian_link(f"daily/daily-{d.isoformat()}", d.strftime("%a %m/%d"))
            lines.append(
                f"| {day_link} | {len(day_sessions)} | "
                f"{format_duration(day_dur)} | {top_tag} |"
            )
        lines.append("")

        # Tool stats
        tools: Counter[str] = Counter()
        for s in sessions:
            for t in s.tools_used:
                tools[t.name] += t.count
        if tools:
            lines.append("## Tool Usage")
            lines.append("")
            lines.append("| Tool | Calls |")
            lines.append("|------|-------|")
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
