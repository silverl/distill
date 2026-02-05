"""Tests for vermas_task_visibility KPI measurer."""

import json
import tempfile
from pathlib import Path

import pytest

from session_insights.measurers.base import KPIResult
from session_insights.measurers.vermas_task_visibility import (
    VERMAS_NOTE_SECTIONS,
    VermasTaskVisibilityMeasurer,
    score_vermas_note,
)


def _write_note(path: Path, content: str) -> Path:
    """Write a note file and return the path."""
    path.write_text(content, encoding="utf-8")
    return path


FULL_VERMAS_NOTE = """\
---
source: vermas
---
# Session

## Timeline
- **Started:** 2024-06-15 10:00:00
- **Duration:** 30 minutes

## Tools Used
_No tools recorded._

## Outcomes
_No outcomes recorded._

## Task Details

- **Task:** complete-task
- **Mission:** full
- **Cycle:** 1
- **Outcome:** approved

### Description

A fully described task.

## Agent Signals

| Time | Agent | Role | Signal | Message |
|------|-------|------|--------|---------|
| 10:00:00 | dev01 | dev | done | Implementation done |
| 11:00:00 | qa01 | qa | approved | Approved |

## Learnings

### Agent: general
- Lesson learned
"""

PARTIAL_VERMAS_NOTE = """\
---
source: vermas
---
# Session

## Timeline
- **Started:** 2024-06-15 14:00:00
- **Duration:** Unknown

## Tools Used
_No tools recorded._

## Outcomes
_No outcomes recorded._

## Task Details

- **Outcome:** done
"""


class TestScoreVermasNote:
    """Tests for the file-based vermas note scoring function."""

    def test_score_full_note(self, tmp_path: Path) -> None:
        """Full vermas note should have all sections present."""
        note = _write_note(tmp_path / "vermas-full.md", FULL_VERMAS_NOTE)
        scores = score_vermas_note(note)
        assert scores["task_description"]
        assert scores["signals"]
        assert scores["learnings"]
        assert scores["cycle_info"]
        assert all(scores.values())

    def test_score_partial_note(self, tmp_path: Path) -> None:
        """Partial vermas note without description content should score False."""
        note = _write_note(tmp_path / "vermas-partial.md", PARTIAL_VERMAS_NOTE)
        scores = score_vermas_note(note)
        assert not scores["task_description"]  # has ## Task Details but no ### Description
        assert not scores["signals"]  # no "## Agent Signals"
        assert not scores["learnings"]  # no "## Learnings"
        assert not scores["cycle_info"]  # no "**Cycle:**"

    def test_score_empty_note(self, tmp_path: Path) -> None:
        """Empty note should have all sections absent."""
        note = _write_note(tmp_path / "vermas-empty.md", "")
        scores = score_vermas_note(note)
        assert all(not v for v in scores.values())

    def test_all_sections_checked(self, tmp_path: Path) -> None:
        """Every declared section is checked."""
        note = _write_note(tmp_path / "vermas-test.md", "")
        scores = score_vermas_note(note)
        assert set(scores.keys()) == {name for name, _ in VERMAS_NOTE_SECTIONS}


class TestVermasTaskVisibilityMeasurer:
    """Tests for the vermas_task_visibility measurer."""

    def test_result_is_kpi_result(self) -> None:
        """Measurer returns a KPIResult."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        assert isinstance(result, KPIResult)
        assert result.kpi == "vermas_task_visibility"
        assert result.target == 90.0

    def test_value_in_range(self) -> None:
        """Measured value is between 0 and 100."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        assert 0.0 <= result.value <= 100.0

    def test_details_contain_note_info(self) -> None:
        """Details include per-note field data."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        assert "total_notes" in result.details
        assert "per_note" in result.details

    def test_json_serialization(self) -> None:
        """Result serializes to valid JSON."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure()
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["kpi"] == "vermas_task_visibility"

    def test_full_note_scores_100(self, tmp_path: Path) -> None:
        """Full vermas note should score 100%."""
        note = _write_note(tmp_path / "vermas-full.md", FULL_VERMAS_NOTE)
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_note_files([note])
        assert result.value == 100.0

    def test_partial_note_scores_below_100(self, tmp_path: Path) -> None:
        """Partial vermas note should score 0% (no ### Description content)."""
        note = _write_note(tmp_path / "vermas-partial.md", PARTIAL_VERMAS_NOTE)
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_note_files([note])
        # No fields present => 0/4 = 0%
        assert result.value == 0.0

    def test_empty_note_scores_0(self, tmp_path: Path) -> None:
        """Empty note should score 0%."""
        note = _write_note(tmp_path / "vermas-empty.md", "")
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_note_files([note])
        assert result.value == 0.0

    def test_multiple_notes_averaged(self, tmp_path: Path) -> None:
        """Score is averaged across all notes."""
        full = _write_note(tmp_path / "vermas-full.md", FULL_VERMAS_NOTE)
        empty = _write_note(tmp_path / "vermas-empty.md", "")
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_note_files([full, empty])
        # full: 4/4, empty: 0/4 => 4/8 = 50%
        assert result.value == 50.0

    def test_empty_list_returns_0(self) -> None:
        """Empty file list gives 0 total notes."""
        measurer = VermasTaskVisibilityMeasurer()
        result = measurer.measure_from_note_files([])
        assert result.details["total_notes"] == 0
