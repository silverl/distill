"""Blog publisher factory and registry."""

from __future__ import annotations

from distill.blog.config import GhostConfig, Platform
from distill.blog.publishers.base import BlogPublisher
from distill.blog.synthesizer import BlogSynthesizer


def create_publisher(
    platform: Platform | str,
    *,
    synthesizer: BlogSynthesizer | None = None,
    ghost_config: GhostConfig | None = None,
    postiz_config: object | None = None,
) -> BlogPublisher:
    """Create a publisher for the given platform.

    Args:
        platform: The target platform.
        synthesizer: Required for social publishers that need LLM re-synthesis.
        ghost_config: Optional Ghost CMS configuration for live publishing.
        postiz_config: Optional PostizConfig for scheduling and API settings.

    Returns:
        A BlogPublisher instance for the platform.

    Raises:
        ValueError: If the platform is unknown.
    """
    if isinstance(platform, str):
        platform = Platform(platform)

    from distill.blog.publishers.ghost import GhostPublisher
    from distill.blog.publishers.linkedin import LinkedInPublisher
    from distill.blog.publishers.markdown import MarkdownPublisher
    from distill.blog.publishers.obsidian import ObsidianPublisher
    from distill.blog.publishers.postiz import PostizBlogPublisher
    from distill.blog.publishers.reddit import RedditPublisher
    from distill.blog.publishers.twitter import TwitterPublisher

    if platform == Platform.GHOST:
        return GhostPublisher(ghost_config=ghost_config)

    if platform == Platform.POSTIZ:
        return PostizBlogPublisher(synthesizer=synthesizer, postiz_config=postiz_config)

    file_publishers: dict[Platform, type[BlogPublisher]] = {
        Platform.OBSIDIAN: ObsidianPublisher,
        Platform.MARKDOWN: MarkdownPublisher,
    }

    social_publishers: dict[Platform, type[BlogPublisher]] = {
        Platform.TWITTER: TwitterPublisher,
        Platform.LINKEDIN: LinkedInPublisher,
        Platform.REDDIT: RedditPublisher,
    }

    if platform in file_publishers:
        return file_publishers[platform]()

    if platform in social_publishers:
        if synthesizer is None:
            raise ValueError(
                f"Platform {platform.value!r} requires a synthesizer for LLM re-synthesis"
            )
        return social_publishers[platform](synthesizer=synthesizer)

    raise ValueError(f"Unknown platform: {platform!r}")
