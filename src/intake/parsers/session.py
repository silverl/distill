"""Session parser — wraps existing session parsers to produce ContentItems.

Bridges the session pipeline (BaseSession) with the intake pipeline
(ContentItem), allowing coding sessions to flow through the same
ingest → understand → publish funnel as external content.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.base import ContentParser
from distill.parsers.models import BaseSession

logger = logging.getLogger(__name__)


def _session_to_content_item(session: BaseSession) -> ContentItem:
    """Map a BaseSession to a ContentItem."""
    # Build a stable ID from session_id
    raw_id = f"session-{session.session_id}"
    item_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]

    # Use narrative if available, else summary
    body = session.narrative or session.summary or ""
    title = session.summary or session.task_description or "Coding session"
    if len(title) > 200:
        title = title[:197] + "..."

    excerpt = (session.summary or "")[:500]

    # Build tags from session tags + tool names + project
    tags = list(session.tags)
    for tool in session.tools_used:
        if tool.name and tool.name not in tags:
            tags.append(tool.name)
    if (
        session.project
        and session.project not in ("(unknown)", "(unassigned)", "")
        and session.project not in tags
    ):
        tags.append(session.project)

    # Build metadata
    metadata: dict[str, object] = {}
    if session.project:
        metadata["project"] = session.project
    if session.tools_used:
        metadata["tools_used"] = [{"name": t.name, "count": t.count} for t in session.tools_used]
    if session.outcomes:
        metadata["outcomes"] = [
            {
                "description": o.description,
                "files_modified": o.files_modified,
                "success": o.success,
            }
            for o in session.outcomes
        ]
    if session.learnings:
        metadata["learnings"] = [
            {"agent": learning.agent, "learnings": learning.learnings}
            for learning in session.learnings
        ]
    duration = session.duration_minutes
    if duration is not None:
        metadata["duration_minutes"] = round(duration, 1)
    if session.task_description:
        metadata["task_description"] = session.task_description
    if session.signals:
        metadata["signals"] = [{"signal": s.signal, "message": s.message} for s in session.signals]

    return ContentItem(
        id=item_id,
        title=title,
        body=body,
        excerpt=excerpt,
        word_count=len(body.split()) if body else 0,
        site_name=session.source or "claude",
        source=ContentSource.SESSION,
        source_id=session.session_id,
        content_type=ContentType.POST,
        tags=tags,
        published_at=session.start_time,
        saved_at=session.start_time or datetime.now(tz=UTC),
        metadata=metadata,
    )


class SessionParser(ContentParser):
    """Wraps existing Claude/Codex/Vermas parsers to produce ContentItems."""

    @property
    def source(self) -> ContentSource:
        return ContentSource.SESSION

    @property
    def is_configured(self) -> bool:
        return self._config.session.is_configured

    def parse(self, since: datetime | None = None) -> list[ContentItem]:
        """Discover and parse sessions, converting to ContentItems.

        Args:
            since: Only return sessions started after this time.

        Returns:
            List of ContentItems derived from coding sessions.
        """
        from distill.core import discover_sessions, parse_sessions

        cfg = self._config.session

        # Determine directories to scan
        dirs_to_scan: list[Path] = []
        if cfg.session_dirs:
            dirs_to_scan.extend(Path(d) for d in cfg.session_dirs)
        if not dirs_to_scan:
            dirs_to_scan.append(Path.cwd())

        # Discover and parse sessions
        all_sessions: list[BaseSession] = []
        seen_ids: set[str] = set()

        for scan_dir in dirs_to_scan:
            if not scan_dir.exists():
                continue
            discovered = discover_sessions(
                scan_dir,
                sources=cfg.sources if cfg.sources else None,
                include_home=cfg.include_global,
            )
            for source_name, roots in discovered.items():
                for root in roots:
                    sessions = parse_sessions(root, source_name)
                    for session in sessions:
                        if session.session_id not in seen_ids:
                            seen_ids.add(session.session_id)
                            all_sessions.append(session)

        # Filter by since date
        if since is not None:
            # Ensure since is timezone-aware for comparison
            if since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
            all_sessions = [
                s for s in all_sessions if s.start_time is not None and s.start_time >= since
            ]

        # Convert to ContentItems
        items: list[ContentItem] = []
        for session in all_sessions:
            items.append(_session_to_content_item(session))

        logger.info("Parsed %d sessions into ContentItems", len(items))
        return items
