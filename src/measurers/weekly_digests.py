"""Weekly digests KPI measurer.

Creates sample sessions spanning multiple weeks, generates weekly
digests, and reports the percentage of weeks with valid digest files.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from distill.core import discover_sessions, parse_session_file
from distill.formatters.weekly import WeeklyDigestFormatter, group_sessions_by_week
from distill.measurers.base import KPIResult, Measurer
from distill.parsers.models import BaseSession

# Markers expected in a valid weekly digest
WEEKLY_DIGEST_MARKERS: list[tuple[str, str]] = [
    ("has_title", "# Weekly Digest:"),
    ("has_overview", "## Overview"),
    ("has_daily_breakdown", "## Daily Breakdown"),
]


def _create_multi_week_data(base: Path) -> None:
    """Create sample Claude sessions spanning two ISO weeks."""
    project_dir = base / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    # Week 1 sessions (Monday and Wednesday)
    week1_mon = datetime(2024, 6, 10, 10, 0, tzinfo=timezone.utc)
    week1_wed = datetime(2024, 6, 12, 14, 0, tzinfo=timezone.utc)

    # Week 2 session (Tuesday)
    week2_tue = datetime(2024, 6, 18, 9, 0, tzinfo=timezone.utc)

    for i, (start, task) in enumerate(
        [
            (week1_mon, "Refactor auth module"),
            (week1_wed, "Add tests for login"),
            (week2_tue, "Deploy to staging"),
        ]
    ):
        entries = [
            {
                "type": "user",
                "timestamp": start.isoformat(),
                "cwd": "/home/user/projects/my-app",
                "sessionId": f"sess-wk-{i}",
                "message": {"content": task},
            },
            {
                "type": "assistant",
                "timestamp": (start + timedelta(minutes=5)).isoformat(),
                "message": {"content": f"Working on: {task}"},
            },
        ]
        session_file = project_dir / f"sess-wk-{i}.jsonl"
        with session_file.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")


def _generate_weekly_digests_to_disk(
    sessions: list[BaseSession], output_dir: Path
) -> list[Path]:
    """Generate weekly digest files and return the paths."""
    digests_dir = output_dir / "weekly"
    digests_dir.mkdir(parents=True, exist_ok=True)

    groups = group_sessions_by_week(sessions)
    formatter = WeeklyDigestFormatter()
    written: list[Path] = []

    for (iso_year, iso_week), week_sessions in groups.items():
        content = formatter.format_weekly_digest(iso_year, iso_week, week_sessions)
        name = formatter.note_name(iso_year, iso_week)
        path = digests_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return written


class WeeklyDigestsMeasurer(Measurer):
    """Measures percentage of weeks with valid generated digests."""

    KPI_NAME = "weekly_digests"
    TARGET = 100.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            return self._measure_from_directory(base)

    def measure_from_output(self, output_dir: Path) -> KPIResult:
        """Measure from pre-generated weekly digest files."""
        digests_dir = output_dir / "weekly"
        if not digests_dir.exists():
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "weekly/ directory not found"},
            )
        note_files = list(digests_dir.glob("weekly-*.md"))
        if not note_files:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no weekly digest files found"},
            )
        return self._score_digest_files(note_files, expected_weeks=len(note_files))

    def _measure_from_directory(self, base: Path) -> KPIResult:
        _create_multi_week_data(base)

        all_sessions: list[BaseSession] = []
        discovered = discover_sessions(base, sources=None)
        for src, paths in discovered.items():
            for path in paths:
                all_sessions.extend(parse_session_file(path, src))

        if not all_sessions:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no sessions parsed"},
            )

        # Count expected weeks
        groups = group_sessions_by_week(all_sessions)
        expected_weeks = len(groups)

        output_dir = base / "output"
        note_files = _generate_weekly_digests_to_disk(all_sessions, output_dir)

        if not note_files:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no weekly digest files generated"},
            )

        return self._score_digest_files(note_files, expected_weeks)

    def _score_digest_files(
        self, note_files: list[Path], expected_weeks: int
    ) -> KPIResult:
        valid_count = 0
        per_digest: list[dict[str, object]] = []

        for path in note_files:
            content = path.read_text(encoding="utf-8")
            scores: dict[str, bool] = {}
            for field_name, marker in WEEKLY_DIGEST_MARKERS:
                scores[field_name] = marker in content
            is_valid = all(scores.values())
            if is_valid:
                valid_count += 1
            per_digest.append(
                {"file": path.name, "scores": scores, "valid": is_valid}
            )

        value = (valid_count / expected_weeks * 100) if expected_weeks > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "expected_weeks": expected_weeks,
                "generated_digests": len(note_files),
                "valid_digests": valid_count,
                "per_digest": per_digest,
            },
        )


if __name__ == "__main__":
    result = WeeklyDigestsMeasurer().measure()
    print(result.to_json())
