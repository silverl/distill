"""Working memory for journal narrative continuity.

Extracts structured memory from generated prose and injects it into
subsequent journal entries, creating a feedback loop where each day's
journal builds on the last.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MEMORY_FILENAME = ".working-memory.json"


class MemoryThread(BaseModel):
    """An ongoing narrative thread that spans multiple days."""

    name: str
    summary: str
    first_mentioned: date
    last_mentioned: date
    status: str = "open"  # open | resolved | stalled


class DailyMemoryEntry(BaseModel):
    """Extracted memory from a single day's journal."""

    date: date
    themes: list[str] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    tomorrow_intentions: list[str] = Field(default_factory=list)


class WorkingMemory(BaseModel):
    """Rolling memory across days."""

    entries: list[DailyMemoryEntry] = Field(default_factory=list)
    threads: list[MemoryThread] = Field(default_factory=list)

    def render_for_prompt(self) -> str:
        """Render memory as text suitable for LLM context injection.

        Returns empty string if no entries exist.
        """
        if not self.entries and not self.threads:
            return ""

        lines: list[str] = ["# Previous Context", ""]

        for entry in self.entries:
            lines.append(f"## {entry.date.isoformat()}")
            if entry.themes:
                lines.append(f"Themes: {', '.join(entry.themes)}")
            if entry.key_insights:
                lines.append("Insights:")
                for insight in entry.key_insights:
                    lines.append(f"  - {insight}")
            if entry.decisions_made:
                lines.append("Decisions:")
                for decision in entry.decisions_made:
                    lines.append(f"  - {decision}")
            if entry.open_questions:
                lines.append("Open questions:")
                for q in entry.open_questions:
                    lines.append(f"  - {q}")
            if entry.tomorrow_intentions:
                lines.append("Planned next:")
                for intention in entry.tomorrow_intentions:
                    lines.append(f"  - {intention}")
            lines.append("")

        open_threads = [t for t in self.threads if t.status == "open"]
        if open_threads:
            lines.append("## Ongoing Threads")
            for thread in open_threads:
                lines.append(
                    f"- {thread.name} (open since {thread.first_mentioned.isoformat()}): "
                    f"{thread.summary}"
                )
            lines.append("")

        return "\n".join(lines)

    def add_entry(self, entry: DailyMemoryEntry) -> None:
        """Add a daily memory entry, replacing any existing entry for the same date."""
        self.entries = [e for e in self.entries if e.date != entry.date]
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.date)

    def prune(self, window_days: int) -> None:
        """Remove entries older than window_days from the most recent entry."""
        if not self.entries:
            return
        latest = max(e.date for e in self.entries)
        cutoff = latest.toordinal() - window_days
        self.entries = [e for e in self.entries if e.date.toordinal() > cutoff]
        # Remove resolved threads that haven't been mentioned within the window
        self.threads = [
            t
            for t in self.threads
            if t.status != "resolved" or t.last_mentioned.toordinal() > cutoff
        ]

    def update_threads(self, threads: list[MemoryThread]) -> None:
        """Merge new thread data into existing threads."""
        by_name = {t.name: t for t in self.threads}
        for thread in threads:
            if thread.name in by_name:
                existing = by_name[thread.name]
                existing.summary = thread.summary
                existing.last_mentioned = thread.last_mentioned
                existing.status = thread.status
            else:
                self.threads.append(thread)
                by_name[thread.name] = thread


def load_memory(output_dir: Path) -> WorkingMemory:
    """Load working memory from disk.

    Returns empty WorkingMemory if file doesn't exist or is corrupt.
    """
    memory_path = output_dir / "journal" / MEMORY_FILENAME
    if not memory_path.exists():
        return WorkingMemory()
    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
        return WorkingMemory.model_validate(data)
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Corrupt memory file at %s, starting fresh", memory_path)
        return WorkingMemory()


def save_memory(memory: WorkingMemory, output_dir: Path) -> None:
    """Save working memory to disk."""
    memory_path = output_dir / "journal" / MEMORY_FILENAME
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        memory.model_dump_json(indent=2),
        encoding="utf-8",
    )
