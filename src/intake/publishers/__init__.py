"""Intake output publishers — fan-out from canonical model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from distill.intake.publishers.base import IntakePublisher

if TYPE_CHECKING:
    from distill.blog.config import GhostConfig


def create_intake_publisher(
    platform: str,
    *,
    ghost_config: GhostConfig | None = None,
) -> IntakePublisher:
    """Create a publisher for the given platform.

    Args:
        platform: Target platform name.
        ghost_config: Optional Ghost CMS configuration (for ``"ghost"``).

    Returns:
        An IntakePublisher instance.

    Raises:
        ValueError: If the platform is unknown.
    """
    from distill.intake.publishers.ghost import GhostIntakePublisher
    from distill.intake.publishers.linkedin import LinkedInIntakePublisher
    from distill.intake.publishers.markdown import MarkdownIntakePublisher
    from distill.intake.publishers.obsidian import ObsidianIntakePublisher
    from distill.intake.publishers.reddit import RedditIntakePublisher
    from distill.intake.publishers.twitter import TwitterIntakePublisher

    # File-only publishers (no LLM needed)
    simple_publishers: dict[str, type[IntakePublisher]] = {
        "obsidian": ObsidianIntakePublisher,
        "markdown": MarkdownIntakePublisher,
    }

    if platform in simple_publishers:
        return simple_publishers[platform]()

    # Social publishers (LLM re-synthesis via Claude CLI)
    social_publishers: dict[str, type[IntakePublisher]] = {
        "twitter": TwitterIntakePublisher,
        "linkedin": LinkedInIntakePublisher,
        "reddit": RedditIntakePublisher,
    }

    if platform in social_publishers:
        return social_publishers[platform]()

    if platform == "ghost":
        return GhostIntakePublisher(ghost_config=ghost_config)

    if platform == "postiz":
        from distill.intake.publishers.postiz import PostizIntakePublisher

        return PostizIntakePublisher()

    raise ValueError(f"Unknown intake publisher: {platform!r}")
