"""Content archiving — persist raw ContentItems for future use."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from distill.intake.models import ContentItem

logger = logging.getLogger(__name__)


def archive_items(
    items: list[ContentItem],
    output_dir: Path,
    target_date: date | None = None,
) -> Path:
    """Save raw content items as a daily JSON archive.

    Args:
        items: Content items to archive.
        output_dir: Root output directory.
        target_date: Date for the archive file. Defaults to today.

    Returns:
        Path to the written archive file.
    """
    if target_date is None:
        target_date = date.today()

    archive_dir = output_dir / "intake" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / f"{target_date.isoformat()}.json"

    # Serialize items — use Pydantic's dict export for clean JSON
    data = {
        "date": target_date.isoformat(),
        "item_count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
    }

    archive_path.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Archived %d items to %s", len(items), archive_path)
    return archive_path


def build_daily_index(
    items: list[ContentItem],
    output_dir: Path,
    target_date: date | None = None,
) -> Path:
    """Build a browseable Obsidian index of all items for the day.

    Creates a markdown file listing every article with title, source,
    author, excerpt, and link — useful for browsing what was ingested.

    Args:
        items: Content items to index.
        output_dir: Root output directory.
        target_date: Date for the index file.

    Returns:
        Path to the written index file.
    """
    if target_date is None:
        target_date = date.today()

    index_dir = output_dir / "intake" / "raw"
    index_dir.mkdir(parents=True, exist_ok=True)

    index_path = index_dir / f"raw-{target_date.isoformat()}.md"

    # Group items by site
    by_site: dict[str, list[ContentItem]] = {}
    for item in items:
        key = item.site_name or item.source.value
        by_site.setdefault(key, []).append(item)

    # Sort sites by item count descending
    sorted_sites = sorted(by_site.items(), key=lambda kv: len(kv[1]), reverse=True)

    lines: list[str] = [
        "---",
        f"date: {target_date.isoformat()}",
        "type: intake-raw-index",
        f"items: {len(items)}",
        f"sources: {len(sorted_sites)}",
        "---",
        f"# Raw Feed Items — {target_date.strftime('%B %d, %Y')}",
        "",
        f"**{len(items)} items** from **{len(sorted_sites)} sources**",
        "",
    ]

    for site_name, site_items in sorted_sites:
        lines.append(f"## {site_name} ({len(site_items)})")
        lines.append("")

        for item in site_items:
            title = item.title or "(untitled)"
            if item.url:
                lines.append(f"### [{title}]({item.url})")
            else:
                lines.append(f"### {title}")

            meta: list[str] = []
            if item.author:
                meta.append(f"by {item.author}")
            if item.published_at:
                meta.append(item.published_at.strftime("%Y-%m-%d %H:%M"))
            if item.word_count:
                meta.append(f"{item.word_count} words")
            if meta:
                lines.append(f"*{' | '.join(meta)}*")

            if item.tags:
                lines.append(f"Tags: {', '.join(item.tags[:8])}")

            excerpt = item.excerpt or (
                item.body[:300] + "..." if item.body and len(item.body) > 300 else item.body
            )
            if excerpt:
                lines.append("")
                lines.append(f"> {excerpt.strip()[:500]}")

            lines.append("")

    index_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Built raw index with %d items at %s", len(items), index_path)
    return index_path
