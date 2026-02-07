"""Obsidian-compatible markdown formatter for blog posts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from distill.blog.context import ThematicBlogContext, WeeklyBlogContext


class BlogFormatter:
    """Formats synthesized blog prose into Obsidian-compatible markdown."""

    def format_weekly(self, context: WeeklyBlogContext, prose: str) -> str:
        """Format a weekly synthesis post with frontmatter and source links.

        Args:
            context: The weekly blog context.
            prose: Synthesized prose from the LLM.

        Returns:
            Complete Obsidian markdown note.
        """
        fm = self._weekly_frontmatter(context)
        body = self._weekly_body(context, prose)
        return fm + body

    def format_thematic(self, context: ThematicBlogContext, prose: str) -> str:
        """Format a thematic deep-dive post with frontmatter and source links.

        Args:
            context: The thematic blog context.
            prose: Synthesized prose from the LLM.

        Returns:
            Complete Obsidian markdown note.
        """
        fm = self._thematic_frontmatter(context)
        body = self._thematic_body(context, prose)
        return fm + body

    def weekly_output_path(self, output_dir: Path, year: int, week: int) -> Path:
        """Compute the output file path for a weekly blog post."""
        return output_dir / "blog" / "weekly" / f"weekly-{year}-W{week:02d}.md"

    def thematic_output_path(self, output_dir: Path, slug: str) -> Path:
        """Compute the output file path for a thematic blog post."""
        return output_dir / "blog" / "themes" / f"{slug}.md"

    def _weekly_frontmatter(self, context: WeeklyBlogContext) -> str:
        lines: list[str] = ["---"]
        lines.append(f"date: {context.week_start.isoformat()}")
        lines.append("type: blog")
        lines.append("blog_type: weekly")
        lines.append(f"week: {context.year}-W{context.week:02d}")
        lines.append(f"sessions_count: {context.total_sessions}")
        lines.append(f"duration_minutes: {context.total_duration_minutes:.0f}")

        if context.projects:
            lines.append("projects:")
            for project in context.projects:
                lines.append(f"  - {project}")

        lines.append("tags:")
        lines.append("  - blog")
        lines.append("  - weekly")
        for tag in context.all_tags[:10]:
            if tag not in ("blog", "weekly"):
                lines.append(f"  - {tag}")

        lines.append(f"created: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _weekly_body(self, context: WeeklyBlogContext, prose: str) -> str:
        lines: list[str] = []

        # Prose body (title comes from the LLM)
        lines.append(prose)
        lines.append("")

        # Sources section
        lines.append("---")
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for entry in sorted(context.entries, key=lambda e: e.date):
            stem = entry.file_path.stem
            date_label = entry.date.strftime("%b %d")
            lines.append(f"- [[journal/{stem}|{date_label} Journal]]")
        lines.append("")

        return "\n".join(lines)

    def _thematic_frontmatter(self, context: ThematicBlogContext) -> str:
        lines: list[str] = ["---"]
        lines.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("type: blog")
        lines.append("blog_type: thematic")
        lines.append(f"theme: {context.theme.slug}")
        lines.append(f"evidence_days: {context.evidence_count}")
        lines.append(
            f"date_range: [{context.date_range[0].isoformat()}, "
            f"{context.date_range[1].isoformat()}]"
        )

        lines.append("tags:")
        lines.append("  - blog")
        lines.append("  - thematic")
        # Add theme slug as tag
        for part in context.theme.slug.split("-"):
            lines.append(f"  - {part}")

        lines.append(f"created: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _thematic_body(self, context: ThematicBlogContext, prose: str) -> str:
        lines: list[str] = []

        # Prose body (title comes from the LLM)
        lines.append(prose)
        lines.append("")

        # Sources section
        lines.append("---")
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for entry in sorted(context.evidence_entries, key=lambda e: e.date):
            stem = entry.file_path.stem
            date_label = entry.date.strftime("%b %d")
            lines.append(f"- [[journal/{stem}|{date_label} Journal]]")
        lines.append("")

        return "\n".join(lines)
