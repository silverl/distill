"""Content source parsers — fan-in to canonical ContentItem model."""

from __future__ import annotations

from distill.intake.config import IntakeConfig
from distill.intake.models import ContentSource
from distill.intake.parsers.base import ContentParser


def create_parser(
    source: ContentSource | str,
    *,
    config: IntakeConfig,
) -> ContentParser:
    """Create a parser for the given source.

    Args:
        source: The content source to create a parser for.
        config: Intake configuration.

    Returns:
        A ContentParser instance. Caller should check ``parser.is_configured``
        before calling ``parse()``.

    Raises:
        ValueError: If the source is unknown.
    """
    if isinstance(source, str):
        source = ContentSource(source)

    from distill.intake.parsers.browser import BrowserParser
    from distill.intake.parsers.gmail import GmailParser
    from distill.intake.parsers.linkedin import LinkedInParser
    from distill.intake.parsers.reddit import RedditParser
    from distill.intake.parsers.rss import RSSParser
    from distill.intake.parsers.session import SessionParser
    from distill.intake.parsers.substack import SubstackParser
    from distill.intake.parsers.twitter import TwitterParser
    from distill.intake.parsers.youtube import YouTubeParser

    parsers: dict[ContentSource, type[ContentParser]] = {
        ContentSource.RSS: RSSParser,
        ContentSource.BROWSER: BrowserParser,
        ContentSource.SUBSTACK: SubstackParser,
        ContentSource.LINKEDIN: LinkedInParser,
        ContentSource.TWITTER: TwitterParser,
        ContentSource.REDDIT: RedditParser,
        ContentSource.YOUTUBE: YouTubeParser,
        ContentSource.GMAIL: GmailParser,
        ContentSource.SESSION: SessionParser,
    }

    if source in parsers:
        return parsers[source](config=config)

    raise ValueError(f"Unknown content source: {source!r}")


def get_configured_parsers(config: IntakeConfig) -> list[ContentParser]:
    """Return all parsers that have valid configuration."""
    result: list[ContentParser] = []
    for source in ContentSource:
        try:
            parser = create_parser(source, config=config)
        except ValueError:
            continue
        if parser.is_configured:
            result.append(parser)
    return result
