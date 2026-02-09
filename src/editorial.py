"""Editorial notes — user steering for content generation.

Editorial notes let you guide what the LLM emphasizes in journal entries,
blog posts, and social posts. Notes can target a specific week, theme,
or apply globally.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

NOTES_FILENAME = ".distill-notes.json"


class EditorialNote(BaseModel):
    """A single editorial steering note."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    text: str
    target: str = ""  # e.g. "week:2026-W06", "theme:multi-agent", "" (global)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    used: bool = False


class EditorialStore:
    """Manages editorial notes in a simple JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path / NOTES_FILENAME
        self._notes: list[EditorialNote] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._notes = []
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._notes = [EditorialNote.model_validate(n) for n in data]
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Corrupt notes file at %s, starting fresh", self._path)
            self._notes = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [n.model_dump(mode="json") for n in self._notes]
        self._path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def add(self, text: str, target: str = "") -> EditorialNote:
        """Add a new editorial note."""
        note = EditorialNote(text=text, target=target)
        self._notes.append(note)
        self._save()
        return note

    def list_active(self, target: str = "") -> list[EditorialNote]:
        """Return active (unused) notes, optionally filtered by target.

        If target is provided, returns notes matching that target plus
        global notes (empty target). If target is empty, returns all
        unused notes.
        """
        result = []
        for n in self._notes:
            if n.used:
                continue
            if target:
                if n.target == target or n.target == "":
                    result.append(n)
            else:
                result.append(n)
        return result

    def list_all(self) -> list[EditorialNote]:
        """Return all notes."""
        return list(self._notes)

    def mark_used(self, note_id: str) -> None:
        """Mark a note as consumed."""
        for note in self._notes:
            if note.id == note_id:
                note.used = True
                self._save()
                return

    def remove(self, note_id: str) -> None:
        """Remove a note by ID."""
        self._notes = [n for n in self._notes if n.id != note_id]
        self._save()

    def render_for_prompt(self, target: str = "") -> str:
        """Render active notes as text for LLM prompt injection."""
        active = self.list_active(target)
        if not active:
            return ""
        lines = ["## Editorial Direction", ""]
        for note in active:
            lines.append(f"- {note.text}")
        return "\n".join(lines)
