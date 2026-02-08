"""Obsidian-formatted intake publisher."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher


class ObsidianIntakePublisher(IntakePublisher):
    """Formats intake digests as Obsidian-compatible markdown."""

    def format_daily(self, context: DailyIntakeContext, prose: str) -> str:
        frontmatter = self._build_frontmatter(context)
        return f"{frontmatter}\n{prose}\n"

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        return output_dir / "intake" / f"intake-{target_date.isoformat()}.md"

    def _build_frontmatter(self, context: DailyIntakeContext) -> str:
        lines = [
            "---",
            f"date: {context.date.isoformat()}",
            "type: intake-digest",
            f"items: {context.total_items}",
            f"word_count: {context.total_word_count}",
        ]
        if context.sources:
            sources_str = ", ".join(context.sources)
            lines.append(f"sources: [{sources_str}]")
        if context.all_tags:
            tags_str = ", ".join(context.all_tags[:10])
            lines.append(f"tags: [{tags_str}]")
        lines.append("---")
        return "\n".join(lines)
