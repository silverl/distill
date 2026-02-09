"""Postiz intake publisher — pushes intake digests to Postiz."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from distill.intake.publishers.base import IntakePublisher

logger = logging.getLogger(__name__)


class PostizIntakePublisher(IntakePublisher):
    """Publisher that pushes intake digests to Postiz as drafts or scheduled posts."""

    def __init__(self, *, postiz_config: Any = None) -> None:
        self._postiz_config = postiz_config

    def format_daily(self, context: Any, prose: str) -> str:
        """Push digest prose to Postiz."""
        from distill.integrations.postiz import PostizClient, PostizConfig

        config = self._postiz_config or PostizConfig.from_env()
        if not config.is_configured:
            logger.warning("Postiz not configured for intake publishing")
            return prose

        try:
            client = PostizClient(config)
            # Auto-detect connected integrations
            integrations = client.list_integrations()
            all_ids = [i.id for i in integrations if i.id]
            if all_ids:
                post_type = config.resolve_post_type()
                scheduled_at = None
                if post_type == "schedule":
                    from distill.integrations.scheduling import next_intake_slot

                    scheduled_at = next_intake_slot(config)

                client.create_post(
                    prose,
                    all_ids,
                    post_type=post_type,
                    scheduled_at=scheduled_at,
                )
                if scheduled_at:
                    logger.info("Scheduled intake digest for %s", scheduled_at)
                else:
                    logger.info("Pushed intake digest draft to Postiz")
        except Exception:
            logger.warning("Failed to push intake digest to Postiz", exc_info=True)

        return prose

    def daily_output_path(self, output_dir: Path, target_date: date) -> Path:
        return output_dir / "intake" / "postiz" / f"digest-{target_date.isoformat()}.md"
