"""Plain markdown intake publisher."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher


class MarkdownIntakePublisher(IntakePublisher):
    """Formats intake digests as plain markdown."""

    def format_daily(self, context: DailyIntakeContext, prose: str) -> str:
        header = (
            f"# Intake Digest — {context.date.isoformat()}\n\n"
            f"*{context.total_items} items from {', '.join(context.sources)}*\n\n"
        )
        return f"{header}{prose}\n"

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        return output_dir / "intake" / "markdown" / f"intake-{target_date.isoformat()}.md"
