"""Seed ideas — lightweight raw thoughts as content source.

A seed is a one-liner, headline, or raw thought that gets woven into
daily digests, blog posts, and content. These are YOUR angles — the
LLM uses them as creative prompts alongside your work and reads.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from distill.intake.models import ContentItem, ContentSource, ContentType
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

SEEDS_FILENAME = ".distill-seeds.json"


class SeedIdea(BaseModel):
    """A raw thought, headline, or topic seed."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    text: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    used: bool = False
    used_in: str | None = None


class SeedStore:
    """Manages seed ideas in a simple JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path / SEEDS_FILENAME
        self._seeds: list[SeedIdea] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._seeds = []
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._seeds = [SeedIdea.model_validate(s) for s in data]
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Corrupt seeds file at %s, starting fresh", self._path)
            self._seeds = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.model_dump(mode="json") for s in self._seeds]
        self._path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def add(self, text: str, tags: list[str] | None = None) -> SeedIdea:
        """Add a new seed idea."""
        seed = SeedIdea(text=text, tags=tags or [])
        self._seeds.append(seed)
        self._save()
        return seed

    def list_unused(self) -> list[SeedIdea]:
        """Return all unused seeds."""
        return [s for s in self._seeds if not s.used]

    def list_all(self) -> list[SeedIdea]:
        """Return all seeds."""
        return list(self._seeds)

    def mark_used(self, seed_id: str, used_in: str) -> None:
        """Mark a seed as consumed by a digest/post."""
        for seed in self._seeds:
            if seed.id == seed_id:
                seed.used = True
                seed.used_in = used_in
                self._save()
                return

    def remove(self, seed_id: str) -> None:
        """Remove a seed by ID."""
        self._seeds = [s for s in self._seeds if s.id != seed_id]
        self._save()

    def to_content_items(self) -> list[ContentItem]:
        """Convert unused seeds to ContentItems for the intake pipeline."""
        items: list[ContentItem] = []
        for seed in self.list_unused():
            item = ContentItem(
                id=f"seed-{seed.id}",
                title=seed.text,
                body=seed.text,
                source=ContentSource.SEEDS,
                source_id=seed.id,
                content_type=ContentType.POST,
                tags=seed.tags,
                published_at=seed.created_at,
                saved_at=seed.created_at,
                metadata={"seed_id": seed.id, "seed_type": "idea"},
            )
            items.append(item)
        return items
