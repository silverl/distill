"""Journal markdown reader for blog context assembly.

Discovers and parses existing journal markdown files from the vault.
Returns structured data without needing raw sessions.
"""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JournalEntry(BaseModel):
    """Parsed journal entry from a markdown file."""

    date: date
    style: str = ""
    sessions_count: int = 0
    duration_minutes: float = 0.0
    tags: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    prose: str = ""
    file_path: Path = Path(".")


def _parse_frontmatter(text: str) -> dict[str, str | list[str]]:
    """Extract YAML frontmatter from markdown text.

    Simple key-value parser -- handles scalar values and YAML lists
    without requiring a heavy YAML dependency.
    """
    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    raw = parts[1].strip()
    result: dict[str, str | list[str]] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in raw.splitlines():
        # List item under a key
        if line.startswith("  - ") and current_key is not None:
            if current_list is None:
                current_list = []
            current_list.append(line.strip().removeprefix("- "))
            continue

        # Flush previous list
        if current_list is not None and current_key is not None:
            result[current_key] = current_list
            current_list = None
            current_key = None

        # Key-value pair
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                result[key] = value
            else:
                # Might be a list header
                current_key = key
                current_list = None
        # Bare key with no value -- start a list
        elif current_key is None and line.strip():
            current_key = line.strip().rstrip(":")

    # Flush trailing list
    if current_list is not None and current_key is not None:
        result[current_key] = current_list

    return result


def _extract_prose(text: str) -> str:
    """Extract the narrative body, stripping frontmatter, title, and metrics footer."""
    # Remove frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else ""
    else:
        body = text

    lines = body.strip().splitlines()

    # Strip leading title line (# ...)
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    # Strip trailing Related section
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "## Related":
            lines = lines[:i]
            break

    # Strip trailing metrics footer (starts with ---)
    while lines and lines[-1].strip() == "":
        lines.pop()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "---":
            lines = lines[:i]
            break

    # Strip trailing/leading blank lines
    text_body = "\n".join(lines).strip()
    return text_body


class JournalReader:
    """Discovers and reads journal entries from the output directory."""

    def read_all(self, journal_dir: Path) -> list[JournalEntry]:
        """Read all journal entries from the journal directory."""
        if not journal_dir.exists():
            return []

        entries: list[JournalEntry] = []
        for md_file in sorted(journal_dir.glob("journal-*.md")):
            entry = self._parse_file(md_file)
            if entry is not None:
                entries.append(entry)

        return sorted(entries, key=lambda e: e.date)

    def read_week(
        self, journal_dir: Path, year: int, week: int
    ) -> list[JournalEntry]:
        """Read journal entries for a specific ISO week."""
        all_entries = self.read_all(journal_dir)
        return [
            e
            for e in all_entries
            if e.date.isocalendar().year == year
            and e.date.isocalendar().week == week
        ]

    def read_date_range(
        self, journal_dir: Path, start: date, end: date
    ) -> list[JournalEntry]:
        """Read journal entries within a date range (inclusive)."""
        all_entries = self.read_all(journal_dir)
        return [e for e in all_entries if start <= e.date <= end]

    def _parse_file(self, path: Path) -> JournalEntry | None:
        """Parse a single journal markdown file into a JournalEntry."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Could not read journal file: %s", path)
            return None

        fm = _parse_frontmatter(text)
        prose = _extract_prose(text)

        # Parse date from frontmatter or filename
        entry_date: date | None = None
        if "date" in fm and isinstance(fm["date"], str):
            with contextlib.suppress(ValueError):
                entry_date = date.fromisoformat(fm["date"])

        if entry_date is None:
            # Try filename: journal-YYYY-MM-DD-style.md
            match = re.search(r"journal-(\d{4}-\d{2}-\d{2})", path.name)
            if match:
                with contextlib.suppress(ValueError):
                    entry_date = date.fromisoformat(match.group(1))

        if entry_date is None:
            logger.warning("Could not determine date for %s", path)
            return None

        # Parse numeric fields
        sessions_count = 0
        if "sessions_count" in fm and isinstance(fm["sessions_count"], str):
            with contextlib.suppress(ValueError):
                sessions_count = int(fm["sessions_count"])

        duration = 0.0
        if "duration_minutes" in fm and isinstance(fm["duration_minutes"], str):
            with contextlib.suppress(ValueError):
                duration = float(fm["duration_minutes"])

        # Parse list fields
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        projects = fm.get("projects", [])
        if isinstance(projects, str):
            projects = [projects]

        style = ""
        raw_style = fm.get("style")
        if isinstance(raw_style, str):
            style = raw_style

        return JournalEntry(
            date=entry_date,
            style=style,
            sessions_count=sessions_count,
            duration_minutes=duration,
            tags=list(tags),
            projects=list(projects),
            prose=prose,
            file_path=path,
        )
