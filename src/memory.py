"""Unified memory — tracks themes across sessions, reads, and posts.

Consolidates journal working memory, intake memory, and blog memory
into a single coherent memory system.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MEMORY_FILENAME = ".distill-memory.json"


class DailyEntry(BaseModel):
    """Memory from a single day across all streams."""

    date: date
    sessions: list[str] = Field(default_factory=list)
    reads: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class MemoryThread(BaseModel):
    """An evolving theme that spans multiple days."""

    name: str
    summary: str
    first_seen: date
    last_seen: date
    mention_count: int = 1
    status: str = "active"


class EntityRecord(BaseModel):
    """A tracked entity (project, technology, person, concept)."""

    name: str
    entity_type: str
    first_seen: date
    last_seen: date
    mention_count: int = 1
    context: list[str] = Field(default_factory=list)


class PublishedRecord(BaseModel):
    """Record of published content."""

    slug: str
    title: str
    post_type: str
    date: date
    platforms: list[str] = Field(default_factory=list)


class UnifiedMemory(BaseModel):
    """One memory system for the entire distill pipeline."""

    model_config = {"arbitrary_types_allowed": True}

    entries: list[DailyEntry] = Field(default_factory=list)
    threads: list[MemoryThread] = Field(default_factory=list)
    entities: dict[str, EntityRecord] = Field(default_factory=dict)
    published: list[PublishedRecord] = Field(default_factory=list)
    _trends_text: str = ""

    def render_for_prompt(self, focus: str = "all") -> str:
        """Render memory context for LLM prompts.

        Args:
            focus: "all", "sessions", "intake", or "blog"

        Returns:
            Rendered markdown string.
        """
        if not self.entries and not self.threads:
            return ""

        lines: list[str] = ["# Memory Context", ""]

        recent = sorted(self.entries, key=lambda e: e.date, reverse=True)[:7]
        for entry in recent:
            lines.append(f"## {entry.date.isoformat()}")

            if focus in ("all", "sessions") and entry.sessions:
                lines.append("Sessions:")
                for s in entry.sessions[:5]:
                    lines.append(f"  - {s}")
            if focus in ("all", "intake") and entry.reads:
                lines.append("Reads:")
                for r in entry.reads[:5]:
                    lines.append(f"  - {r}")
            if entry.themes:
                lines.append(f"Themes: {', '.join(entry.themes)}")
            if entry.insights:
                lines.append("Insights:")
                for insight in entry.insights[:3]:
                    lines.append(f"  - {insight}")
            if entry.decisions:
                lines.append("Decisions:")
                for d in entry.decisions[:3]:
                    lines.append(f"  - {d}")
            if entry.open_questions:
                lines.append("Open questions:")
                for q in entry.open_questions[:3]:
                    lines.append(f"  - {q}")
            lines.append("")

        active_threads = [t for t in self.threads if t.status == "active"]
        if active_threads:
            lines.append("## Ongoing Threads")
            for thread in active_threads:
                lines.append(
                    f"- **{thread.name}** ({thread.mention_count}x since "
                    f"{thread.first_seen.isoformat()}): {thread.summary}"
                )
            lines.append("")

        # Entity context — top entities by mention count
        if self.entities:
            top_entities = sorted(
                self.entities.values(),
                key=lambda e: e.mention_count,
                reverse=True,
            )[:10]
            if top_entities:
                lines.append("## What You've Been Working On")
                for entity in top_entities:
                    days_span = (entity.last_seen - entity.first_seen).days + 1
                    lines.append(
                        f"- **{entity.name}** ({entity.entity_type}): "
                        f"{entity.mention_count}x over {days_span} days"
                    )
                lines.append("")

        # Trends (injected externally or computed here)
        if hasattr(self, "_trends_text") and self._trends_text:
            lines.append(self._trends_text)

        if focus in ("all", "blog") and self.published:
            recent_pub = sorted(self.published, key=lambda p: p.date, reverse=True)[:5]
            lines.append("## Recently Published")
            for pub in recent_pub:
                platforms = ", ".join(pub.platforms) if pub.platforms else "unpublished"
                lines.append(f'- "{pub.title}" ({pub.date.isoformat()}, {platforms})')
            lines.append("")

        return "\n".join(lines)

    def inject_trends(self, trends_text: str) -> None:
        """Inject pre-rendered trends text into the memory prompt output."""
        self._trends_text = trends_text

    def add_entry(self, entry: DailyEntry) -> None:
        """Add or replace a daily entry."""
        self.entries = [e for e in self.entries if e.date != entry.date]
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.date)

    def update_threads(self, threads: list[MemoryThread]) -> None:
        """Merge new thread data into existing threads."""
        by_name = {t.name: t for t in self.threads}
        for thread in threads:
            if thread.name in by_name:
                existing = by_name[thread.name]
                existing.summary = thread.summary
                existing.last_seen = thread.last_seen
                existing.mention_count += 1
                existing.status = thread.status
            else:
                self.threads.append(thread)
                by_name[thread.name] = thread

    def track_entity(
        self,
        name: str,
        entity_type: str,
        seen_date: date,
        context: str = "",
    ) -> None:
        """Track or update an entity mention."""
        key = f"{entity_type}:{name.lower()}"
        if key in self.entities:
            entity = self.entities[key]
            entity.last_seen = seen_date
            entity.mention_count += 1
            if context and len(entity.context) < 10:
                entity.context.append(context)
        else:
            self.entities[key] = EntityRecord(
                name=name,
                entity_type=entity_type,
                first_seen=seen_date,
                last_seen=seen_date,
                context=[context] if context else [],
            )

    def add_published(self, record: PublishedRecord) -> None:
        """Record a published piece of content."""
        self.published = [p for p in self.published if p.slug != record.slug]
        self.published.append(record)

    def prune(self, keep_days: int = 30) -> None:
        """Remove old entries and resolved threads."""
        if not self.entries:
            return
        cutoff = max(e.date for e in self.entries).toordinal() - keep_days
        self.entries = [e for e in self.entries if e.date.toordinal() > cutoff]
        self.threads = [
            t for t in self.threads if t.status != "resolved" or t.last_seen.toordinal() > cutoff
        ]


def load_unified_memory(output_dir: Path) -> UnifiedMemory:
    """Load unified memory from disk.

    On first run, migrates from existing memory files if found.
    """
    memory_path = output_dir / MEMORY_FILENAME
    if memory_path.exists():
        try:
            data = json.loads(memory_path.read_text(encoding="utf-8"))
            return UnifiedMemory.model_validate(data)
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Corrupt unified memory at %s, starting fresh", memory_path)

    # Attempt migration from existing memory files
    memory = UnifiedMemory()

    # Migrate from working memory (journal)
    journal_memory = output_dir / "journal" / ".working-memory.json"
    if journal_memory.exists():
        try:
            data = json.loads(journal_memory.read_text(encoding="utf-8"))
            for entry_data in data.get("entries", []):
                memory.add_entry(
                    DailyEntry(
                        date=date.fromisoformat(entry_data["date"]),
                        sessions=entry_data.get("key_insights", []),
                        themes=entry_data.get("themes", []),
                        insights=entry_data.get("key_insights", []),
                        decisions=entry_data.get("decisions_made", []),
                        open_questions=entry_data.get("open_questions", []),
                    )
                )
            for thread_data in data.get("threads", []):
                memory.threads.append(
                    MemoryThread(
                        name=thread_data["name"],
                        summary=thread_data.get("summary", ""),
                        first_seen=date.fromisoformat(thread_data["first_mentioned"]),
                        last_seen=date.fromisoformat(thread_data["last_mentioned"]),
                        status=thread_data.get("status", "active"),
                    )
                )
            logger.info("Migrated journal working memory")
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Could not migrate journal memory")

    # Migrate from intake memory
    intake_memory = output_dir / "intake" / ".intake-memory.json"
    if intake_memory.exists():
        try:
            data = json.loads(intake_memory.read_text(encoding="utf-8"))
            for entry_data in data.get("entries", []):
                entry_date = date.fromisoformat(entry_data["date"])
                # Find existing entry for this date or create new
                existing = next((e for e in memory.entries if e.date == entry_date), None)
                if existing:
                    existing.reads = entry_data.get("key_items", [])
                    existing.themes.extend(entry_data.get("themes", []))
                else:
                    memory.add_entry(
                        DailyEntry(
                            date=entry_date,
                            reads=entry_data.get("key_items", []),
                            themes=entry_data.get("themes", []),
                        )
                    )
            logger.info("Migrated intake memory")
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Could not migrate intake memory")

    # Migrate from blog memory
    blog_memory = output_dir / "blog" / ".blog-memory.json"
    if blog_memory.exists():
        try:
            data = json.loads(blog_memory.read_text(encoding="utf-8"))
            for post_data in data.get("posts", []):
                memory.add_published(
                    PublishedRecord(
                        slug=post_data["slug"],
                        title=post_data.get("title", ""),
                        post_type=post_data.get("post_type", ""),
                        date=date.fromisoformat(post_data["date"]),
                        platforms=post_data.get("platforms_published", []),
                    )
                )
            logger.info("Migrated blog memory")
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Could not migrate blog memory")

    return memory


def save_unified_memory(memory: UnifiedMemory, output_dir: Path) -> None:
    """Save unified memory to disk."""
    memory_path = output_dir / MEMORY_FILENAME
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(memory.model_dump_json(indent=2), encoding="utf-8")
