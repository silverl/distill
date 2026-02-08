"""Ghost CMS-compatible intake publisher with optional live API publishing."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from distill.blog.config import GhostConfig
from distill.intake.context import DailyIntakeContext
from distill.intake.publishers.base import IntakePublisher

logger = logging.getLogger(__name__)


class GhostIntakePublisher(IntakePublisher):
    """Formats intake digests as Ghost-compatible markdown.

    Generates clean markdown with a ``<!-- ghost-meta: {...} -->`` HTML
    comment containing title, date, tags, and status.  When a configured
    :class:`GhostConfig` is provided, the digest is also published to
    the Ghost Admin API via :class:`GhostAPIClient`.

    When *ghost_config* is ``None`` or not fully configured, the
    publisher operates in **file-only** mode: it still produces the
    formatted markdown file but skips the API call.
    """

    def __init__(self, ghost_config: GhostConfig | None = None) -> None:
        self._config = ghost_config
        self._api: object | None = None
        if ghost_config and ghost_config.is_configured:
            from distill.blog.publishers.ghost import GhostAPIClient

            self._api = GhostAPIClient(ghost_config)

    def format_daily(self, context: DailyIntakeContext, prose: str) -> str:
        """Format a daily intake digest for Ghost CMS.

        Returns Ghost-flavored markdown with a ``ghost-meta`` HTML
        comment at the top.  If the Ghost API is configured, the post
        is also published to Ghost.
        """
        meta_comment = self._build_ghost_meta(context)
        content = f"{meta_comment}{prose}\n"
        self._publish_to_api(content)
        return content

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        return output_dir / "intake" / "ghost" / f"ghost-{target_date.isoformat()}.md"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ghost_meta(self, context: DailyIntakeContext) -> str:
        """Build the ghost-meta HTML comment for the digest."""
        title = f"Daily Research Digest \u2014 {context.date.strftime('%B %-d, %Y')}"
        tags = list(context.all_tags[:10])
        meta = {
            "title": title,
            "date": context.date.isoformat(),
            "tags": tags,
            "status": "draft",
        }
        return f"<!-- ghost-meta: {json.dumps(meta)} -->\n\n"

    def _parse_ghost_meta(self, content: str) -> dict:
        """Extract ghost-meta JSON from content."""
        if "<!-- ghost-meta:" not in content:
            return {}
        try:
            meta_str = content.split("<!-- ghost-meta:")[1].split("-->")[0].strip()
            return json.loads(meta_str)
        except (IndexError, json.JSONDecodeError):
            return {}

    def _publish_to_api(self, content: str) -> dict | None:
        """Publish content to Ghost API if configured.

        Returns the API response dict, or ``None`` if not configured or
        on error.  Errors are logged but never raised so the local file
        is always written regardless of API failures.
        """
        if not self._api or not self._config:
            return None

        meta = self._parse_ghost_meta(content)
        if not meta:
            return None

        title = meta.get("title", "Untitled")
        tags = meta.get("tags", [])

        # Strip the ghost-meta comment before sending to the API
        prose = content.split("-->\n\n", 1)[-1] if "-->\n\n" in content else content

        try:
            if self._config.newsletter_slug:
                post = self._api.create_post(title, prose, tags, status="draft")
                post = self._api.publish_with_newsletter(post["id"], self._config.newsletter_slug)
                logger.info("Published intake digest '%s' to Ghost with newsletter", title)
                return post
            else:
                status = "published" if self._config.auto_publish else "draft"
                post = self._api.create_post(title, prose, tags, status=status)
                logger.info("Published intake digest '%s' to Ghost as %s", title, status)
                return post
        except Exception:
            logger.warning(
                "Failed to publish intake digest '%s' to Ghost API", title, exc_info=True
            )
            return None
