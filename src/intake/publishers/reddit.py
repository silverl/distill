"""Reddit discussion post publisher for intake digests."""

from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher

logger = logging.getLogger(__name__)

REDDIT_SYSTEM_PROMPT = (
    "Adapt this daily research digest for a Reddit discussion post "
    "(r/programming or r/technology).\n"
    "Structure:\n"
    "- **TL;DR** (2-3 sentences capturing the day's most important finding)\n"
    "- **What I Read Today** (3-5 bullet points with links)\n"
    "- Brief narrative (2-3 paragraphs, casual but informed tone, ~400-600 words)\n"
    "- **Discussion question** (engaging, open-ended, invites debate)\n"
    "Output ONLY the post, no commentary."
)


class RedditIntakePublisher(IntakePublisher):
    """Adapts intake digests into Reddit discussion posts via Claude CLI."""

    requires_llm = True

    def format_daily(self, context: DailyIntakeContext, prose: str) -> str:
        """Format a daily intake digest as a Reddit discussion post.

        Calls Claude CLI to adapt the prose for Reddit. Returns empty
        string on failure so the pipeline can continue.
        """
        prompt = f"{REDDIT_SYSTEM_PROMPT}\n\n---\n\n{prose}"

        try:
            result = subprocess.run(
                ["claude", "-p"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning("Claude CLI failed for Reddit adaptation: %s", e)
            return ""

        if result.returncode != 0:
            err_text = result.stderr.strip() if result.stderr else ""
            logger.warning(
                "Claude CLI exited %d for Reddit adaptation: %s",
                result.returncode,
                err_text,
            )
            return ""

        return result.stdout.strip()

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        """Compute the output file path for a Reddit daily digest."""
        return output_dir / "intake" / "social" / "reddit" / f"reddit-{target_date}.md"
