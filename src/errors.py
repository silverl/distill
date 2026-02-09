"""Structured error reporting for pipeline runs."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPORT_FILENAME = ".distill-last-run.json"


class PipelineError(BaseModel):
    """A single error captured during a pipeline run."""

    stage: str
    source: str = ""
    error_type: str = "unknown"
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    recoverable: bool = True


class PipelineReport(BaseModel):
    """Summary report of a pipeline run."""

    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None
    stages_completed: list[str] = Field(default_factory=list)
    errors: list[PipelineError] = Field(default_factory=list)
    items_processed: dict[str, int] = Field(default_factory=dict)
    outputs_written: list[str] = Field(default_factory=list)

    def add_error(
        self,
        stage: str,
        message: str,
        *,
        source: str = "",
        error_type: str = "unknown",
        recoverable: bool = True,
    ) -> None:
        """Record an error during pipeline execution."""
        self.errors.append(
            PipelineError(
                stage=stage,
                source=source,
                error_type=error_type,
                message=message,
                recoverable=recoverable,
            )
        )

    def mark_stage_complete(self, stage: str) -> None:
        """Record that a pipeline stage completed."""
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)

    def finish(self) -> None:
        """Mark the report as finished."""
        self.finished_at = datetime.now()

    @property
    def success(self) -> bool:
        """True if no unrecoverable errors occurred."""
        return not any(not e.recoverable for e in self.errors)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def summary_text(self) -> str:
        """Human-readable summary of the pipeline run."""
        duration = ""
        if self.finished_at and self.started_at:
            secs = (self.finished_at - self.started_at).total_seconds()
            duration = f" in {secs:.0f}s" if secs < 60 else f" in {secs / 60:.1f}m"

        status = "completed" if self.success else "failed"
        lines = [f"Pipeline {status}{duration}"]

        if self.stages_completed:
            lines.append(f"Stages: {', '.join(self.stages_completed)}")

        if self.items_processed:
            parts = [f"{k}: {v}" for k, v in self.items_processed.items()]
            lines.append(f"Processed: {', '.join(parts)}")

        if self.outputs_written:
            lines.append(f"Outputs: {len(self.outputs_written)} files")

        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
            for err in self.errors[:5]:
                prefix = "[recoverable]" if err.recoverable else "[FATAL]"
                lines.append(f"  {prefix} {err.stage}: {err.message}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        return "\n".join(lines)

    def to_notification_payload(self) -> dict[str, object]:
        """Build a payload suitable for Slack/ntfy notifications."""
        return {
            "status": "success" if self.success else "failure",
            "summary": self.summary_text(),
            "error_count": self.error_count,
            "stages": self.stages_completed,
            "outputs": len(self.outputs_written),
        }


def save_report(report: PipelineReport, output_dir: Path) -> Path:
    """Save the pipeline report to disk."""
    report_path = output_dir / REPORT_FILENAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report_path


def load_report(output_dir: Path) -> PipelineReport | None:
    """Load the last pipeline report from disk."""
    report_path = output_dir / REPORT_FILENAME
    if not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return PipelineReport.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Corrupt report at %s", report_path)
        return None
