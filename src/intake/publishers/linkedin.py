"""LinkedIn post publisher for intake digests."""

from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher

logger = logging.getLogger(__name__)

LINKEDIN_SYSTEM_PROMPT = (
    "Condense this daily research digest into a LinkedIn post (1000-1300 characters total).\n"
    "Professional but accessible tone. Structure:\n"
    "- Hook paragraph that highlights the most provocative finding\n"
    "- 3-4 key takeaways (use emoji bullets: \U0001f511, \U0001f4a1, \u26a1, \U0001f50d)\n"
    "- Closing insight or question to drive engagement\n"
    "- 3-5 relevant hashtags (#AI #Engineering #TechLeadership etc.)\n"
    "Output ONLY the post, no commentary."
)


class LinkedInIntakePublisher(IntakePublisher):
    """Adapts daily intake digests into LinkedIn posts via Claude CLI."""

    requires_llm: bool = True

    def format_daily(self, context: DailyIntakeContext, prose: str) -> str:
        """Format a daily digest as a LinkedIn post by calling Claude CLI.

        Args:
            context: The daily intake context.
            prose: The canonical digest prose to adapt.

        Returns:
            LinkedIn-formatted post text, or empty string on failure.
        """
        prompt = f"{LINKEDIN_SYSTEM_PROMPT}\n\n---\n\n{prose}"

        try:
            result = subprocess.run(
                ["claude", "-p"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning("Claude CLI failed for LinkedIn intake post: %s", e)
            return ""

        if result.returncode != 0:
            err_text = result.stderr.strip() if result.stderr else "(no stderr)"
            logger.warning(
                "Claude CLI exited %d for LinkedIn intake post: %s",
                result.returncode,
                err_text,
            )
            return ""

        return result.stdout.strip()

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        """Compute the output path for a LinkedIn intake post."""
        return (
            output_dir / "intake" / "social" / "linkedin" / f"linkedin-{target_date.isoformat()}.md"
        )
