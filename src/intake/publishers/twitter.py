"""Twitter/X thread publisher for intake digests."""

from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path

from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher

logger = logging.getLogger(__name__)

TWITTER_SYSTEM_PROMPT = """\
Convert this daily research digest into a Twitter/X thread of 5-8 tweets.
Each tweet MUST be 280 characters or fewer.
First tweet is the hook — make it compelling and standalone.
Number each tweet (1/, 2/, etc.).
Include relevant links from the digest where useful.
Last tweet: summarize the day's key theme with a brief CTA.
Output ONLY the thread, no commentary."""


class TwitterIntakePublisher(IntakePublisher):
    """Adapts intake digests into Twitter/X threads via Claude CLI."""

    requires_llm = True

    def format_daily(self, context: DailyIntakeContext, prose: str) -> str:
        """Format a daily intake digest as a Twitter/X thread.

        Calls the Claude CLI to adapt the prose into a numbered thread.
        Returns an empty string if the CLI call fails.
        """
        prompt = f"{TWITTER_SYSTEM_PROMPT}\n\n---\n\n{prose}"

        try:
            result = subprocess.run(
                ["claude", "-p"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning("Claude CLI failed for Twitter adaptation: %s", e)
            return ""

        if result.returncode != 0:
            logger.warning(
                "Claude CLI exited %d for Twitter adaptation: %s",
                result.returncode,
                result.stderr.strip() if result.stderr else "",
            )
            return ""

        return result.stdout.strip()

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        """Compute the output file path for a Twitter thread digest."""
        return output_dir / "intake" / "social" / "twitter" / f"twitter-{target_date}.md"
