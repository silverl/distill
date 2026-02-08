"""Intake state tracking — avoid re-processing content."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

STATE_FILENAME = ".intake-state.json"


class IntakeRecord(BaseModel):
    """Record of a processed content item."""

    item_id: str
    url: str = ""
    title: str = ""
    source: str = ""
    processed_at: datetime = Field(default_factory=datetime.now)


class IntakeState(BaseModel):
    """Tracks which content items have been processed."""

    records: list[IntakeRecord] = Field(default_factory=list)
    last_run: datetime | None = None

    def is_processed(self, item_id: str) -> bool:
        return any(r.item_id == item_id for r in self.records)

    def mark_processed(self, record: IntakeRecord) -> None:
        self.records = [r for r in self.records if r.item_id != record.item_id]
        self.records.append(record)

    def prune(self, keep_days: int = 30) -> None:
        """Remove records older than ``keep_days``."""
        cutoff = datetime.now().timestamp() - keep_days * 86400
        self.records = [r for r in self.records if r.processed_at.timestamp() > cutoff]


def load_intake_state(output_dir: Path) -> IntakeState:
    """Load intake state from disk."""
    state_path = output_dir / "intake" / STATE_FILENAME
    if not state_path.exists():
        return IntakeState()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return IntakeState.model_validate(data)
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Corrupt intake state at %s, starting fresh", state_path)
        return IntakeState()


def save_intake_state(state: IntakeState, output_dir: Path) -> None:
    """Save intake state to disk."""
    state_path = output_dir / "intake" / STATE_FILENAME
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
