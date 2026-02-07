"""Obsidian-compatible markdown formatter for journal entries."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from distill.journal.config import JournalConfig, JournalStyle
from distill.journal.context import DailyContext


class JournalFormatter:
    """Formats synthesized prose into Obsidian-compatible markdown."""

    def __init__(self, config: JournalConfig) -> None:
        self._config = config

    def format_entry(self, context: DailyContext, prose: str) -> str:
        """Wrap prose in YAML frontmatter and Obsidian links.

        Args:
            context: The daily context used for metadata.
            prose: Synthesized prose from the LLM.

        Returns:
            Complete Obsidian markdown note.
        """
        frontmatter = self._build_frontmatter(context)
        body = self._build_body(context, prose)
        return frontmatter + body

    def output_path(self, output_dir: Path, context: DailyContext) -> Path:
        """Compute the output file path for a journal entry."""
        journal_dir = output_dir / "journal"
        filename = f"journal-{context.date.isoformat()}-{self._config.style.value}.md"
        return journal_dir / filename

    def _build_frontmatter(self, context: DailyContext) -> str:
        lines: list[str] = ["---"]
        lines.append(f"date: {context.date.isoformat()}")
        lines.append(f"type: journal")
        lines.append(f"style: {self._config.style.value}")
        lines.append(f"sessions_count: {context.total_sessions}")
        lines.append(f"duration_minutes: {context.total_duration_minutes:.0f}")

        if context.tags:
            lines.append("tags:")
            lines.append("  - journal")
            for tag in context.tags[:10]:
                lines.append(f"  - {tag}")
        else:
            lines.append("tags:")
            lines.append("  - journal")

        if context.projects_worked:
            lines.append("projects:")
            for project in context.projects_worked:
                lines.append(f"  - {project}")

        lines.append(f"created: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _build_body(self, context: DailyContext, prose: str) -> str:
        lines: list[str] = []

        # Title
        date_str = context.date.strftime("%B %d, %Y")
        style_label = _style_display_name(self._config.style)
        lines.append(f"# {style_label}: {date_str}")
        lines.append("")

        # Prose body
        lines.append(prose)
        lines.append("")

        # Metrics footer (optional)
        if self._config.include_metrics:
            lines.append("---")
            lines.append("")
            lines.append(
                f"*{context.total_sessions} sessions "
                f"| {context.total_duration_minutes:.0f} minutes"
            )
            if context.projects_worked:
                lines.append(
                    f"| Projects: {', '.join(context.projects_worked)}"
                )
            lines.append("*")
            lines.append("")

        # Related notes links
        lines.append("## Related")
        lines.append("")
        daily_link = f"[[daily/daily-{context.date.isoformat()}|Daily Summary]]"
        lines.append(f"- {daily_link}")
        lines.append("")

        return "\n".join(lines)


def _style_display_name(style: JournalStyle) -> str:
    """Human-readable display name for a journal style."""
    return {
        JournalStyle.DEV_JOURNAL: "Dev Journal",
        JournalStyle.TECH_BLOG: "Tech Blog",
        JournalStyle.TEAM_UPDATE: "Team Update",
        JournalStyle.BUILDING_IN_PUBLIC: "Building in Public",
    }[style]
