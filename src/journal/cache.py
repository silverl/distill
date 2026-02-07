"""Incremental generation tracking for journal entries."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from distill.journal.config import JournalStyle

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """Cached state for a single journal entry."""

    session_count: int
    generated_at: str  # ISO timestamp


class JournalCache:
    """Tracks which journal entries have been generated.

    Cache file lives at ``{output_dir}/journal/.journal-cache.json``
    and maps ``"date:style"`` keys to CacheEntry values.
    """

    def __init__(self, output_dir: Path) -> None:
        self._cache_path = output_dir / "journal" / ".journal-cache.json"
        self._data: dict[str, CacheEntry] = self._load()

    def _load(self) -> dict[str, CacheEntry]:
        if not self._cache_path.exists():
            return {}
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return {k: CacheEntry.model_validate(v) for k, v in raw.items()}
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to load journal cache: %s", e)
            return {}

    def _save(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {k: v.model_dump() for k, v in self._data.items()}
        self._cache_path.write_text(
            json.dumps(raw, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _key(target_date: date, style: JournalStyle) -> str:
        return f"{target_date.isoformat()}:{style.value}"

    def is_generated(
        self, target_date: date, style: JournalStyle, session_count: int
    ) -> bool:
        """Check if an entry is already cached with the same session count."""
        key = self._key(target_date, style)
        entry = self._data.get(key)
        if entry is None:
            return False
        return entry.session_count == session_count

    def mark_generated(
        self, target_date: date, style: JournalStyle, session_count: int
    ) -> None:
        """Record that a journal entry has been generated."""
        key = self._key(target_date, style)
        self._data[key] = CacheEntry(
            session_count=session_count,
            generated_at=datetime.now().isoformat(),
        )
        self._save()
