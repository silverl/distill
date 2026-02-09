"""Postiz blog publisher — pushes drafts/scheduled posts to Postiz."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from distill.blog.publishers.base import BlogPublisher

logger = logging.getLogger(__name__)


class PostizBlogPublisher(BlogPublisher):
    """Publisher that pushes blog content to Postiz as drafts or scheduled posts.

    Uses the existing ``synthesizer.adapt_for_platform()`` for LLM adaptation,
    then creates a post in Postiz for review/scheduling.
    """

    requires_llm = True

    def __init__(
        self,
        *,
        synthesizer: Any = None,
        postiz_config: Any = None,
        target_platforms: list[str] | None = None,
    ) -> None:
        self._synthesizer = synthesizer
        self._postiz_config = postiz_config
        self._target_platforms = target_platforms  # None = auto-detect from Postiz
        self._used_thematic_dates: set[str] = set()

    def format_weekly(self, context: Any, prose: str) -> str:
        """Adapt weekly prose for social platforms and push to Postiz."""
        editorial_hint = getattr(context, "editorial_notes", "") or ""
        return self._adapt_and_push(
            prose, context_label="weekly", post_kind="weekly", editorial_hint=editorial_hint
        )

    def format_thematic(self, context: Any, prose: str) -> str:
        """Adapt thematic prose for social platforms and push to Postiz."""
        editorial_hint = getattr(context, "editorial_notes", "") or ""
        return self._adapt_and_push(
            prose, context_label="thematic", post_kind="thematic", editorial_hint=editorial_hint
        )

    def weekly_output_path(self, output_dir: Path, year: int, week: int) -> Path:
        return output_dir / "blog" / "postiz" / f"weekly-{year}-W{week:02d}.md"

    def thematic_output_path(self, output_dir: Path, slug: str) -> Path:
        return output_dir / "blog" / "postiz" / f"{slug}.md"

    def format_index(self, output_dir: Path, state: Any) -> str:
        return ""  # No index for Postiz

    def index_path(self, output_dir: Path) -> Path:
        return output_dir / "blog" / "postiz" / "index.md"

    def _adapt_and_push(
        self, prose: str, context_label: str, post_kind: str, editorial_hint: str = ""
    ) -> str:
        """Adapt prose for each target platform and push posts."""
        from distill.integrations.mapping import resolve_integration_ids
        from distill.integrations.postiz import PostizClient, PostizConfig

        config = self._postiz_config or PostizConfig.from_env()

        if not config.is_configured:
            logger.warning("Postiz not configured, writing local file only")
            return prose

        try:
            client = PostizClient(config)
            if self._target_platforms:
                integration_map = resolve_integration_ids(client, self._target_platforms)
            else:
                # Auto-detect: use all connected integrations
                integrations = client.list_integrations()
                integration_map = {}
                for integ in integrations:
                    platform = integ.provider or integ.identifier
                    if platform:
                        integration_map.setdefault(platform, []).append(integ.id)
        except Exception:
            logger.warning("Failed to connect to Postiz, writing local file only", exc_info=True)
            return prose

        # Resolve scheduling
        post_type = config.resolve_post_type()
        scheduled_at = None
        if post_type == "schedule":
            scheduled_at = self._compute_schedule(config, post_kind)

        results: list[str] = [f"# Postiz Drafts ({context_label})", ""]

        for platform, integration_ids in integration_map.items():
            # Adapt content for this platform
            adapted = prose
            if self._synthesizer and hasattr(self._synthesizer, "adapt_for_platform"):
                try:
                    adapted = self._synthesizer.adapt_for_platform(
                        prose, platform, context_label, editorial_hint=editorial_hint
                    )
                except Exception:
                    logger.warning("Failed to adapt for %s, using raw prose", platform)

            # Push post to Postiz
            try:
                client.create_post(
                    adapted,
                    integration_ids,
                    post_type=post_type,
                    scheduled_at=scheduled_at,
                )
                results.append(f"## {platform}")
                if scheduled_at:
                    results.append(
                        f"Scheduled for {scheduled_at} (IDs: {', '.join(integration_ids)})"
                    )
                else:
                    results.append(f"Draft created (IDs: {', '.join(integration_ids)})")
                results.append("")
                results.append(adapted)
                results.append("")
            except Exception:
                logger.warning("Failed to push to Postiz for %s", platform, exc_info=True)
                results.append(f"## {platform} (FAILED)")
                results.append(adapted)
                results.append("")

        return "\n".join(results)

    def _compute_schedule(self, config: Any, post_kind: str) -> str | None:
        """Compute the scheduled_at datetime based on post kind."""
        from distill.integrations.scheduling import next_thematic_slot, next_weekly_slot

        if post_kind == "weekly":
            return next_weekly_slot(config)
        elif post_kind == "thematic":
            slot = next_thematic_slot(config, used_dates=self._used_thematic_dates)
            # Track the date so subsequent thematic posts don't collide
            date_part = slot[:10]
            self._used_thematic_dates.add(date_part)
            return slot
        return None
