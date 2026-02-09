"""Tests for src/errors.py — PipelineError, PipelineReport."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from distill.errors import (
    PipelineError,
    PipelineReport,
    load_report,
    save_report,
)


class TestPipelineError:
    def test_basic_error(self):
        err = PipelineError(stage="journal", message="synthesis failed")
        assert err.stage == "journal"
        assert err.recoverable is True
        assert err.error_type == "unknown"

    def test_non_recoverable_error(self):
        err = PipelineError(stage="intake", message="crash", recoverable=False)
        assert err.recoverable is False


class TestPipelineReport:
    def test_empty_report_success(self):
        report = PipelineReport()
        assert report.success is True
        assert report.error_count == 0

    def test_add_error(self):
        report = PipelineReport()
        report.add_error("journal", "test error", source="rss", error_type="parse_error")
        assert report.error_count == 1
        assert report.errors[0].stage == "journal"
        assert report.errors[0].source == "rss"

    def test_success_with_recoverable_errors(self):
        report = PipelineReport()
        report.add_error("intake", "minor issue", recoverable=True)
        assert report.success is True

    def test_failure_with_unrecoverable_error(self):
        report = PipelineReport()
        report.add_error("blog", "critical failure", recoverable=False)
        assert report.success is False

    def test_mark_stage_complete(self):
        report = PipelineReport()
        report.mark_stage_complete("journal")
        report.mark_stage_complete("journal")  # duplicate ignored
        assert report.stages_completed == ["journal"]

    def test_finish(self):
        report = PipelineReport()
        assert report.finished_at is None
        report.finish()
        assert report.finished_at is not None

    def test_summary_text_success(self):
        report = PipelineReport()
        report.mark_stage_complete("journal")
        report.items_processed = {"journal": 3}
        report.outputs_written = ["a.md", "b.md", "c.md"]
        report.finish()
        text = report.summary_text()
        assert "completed" in text
        assert "journal" in text
        assert "3 files" in text

    def test_summary_text_with_errors(self):
        report = PipelineReport()
        report.add_error("intake", "fetch failed", source="rss")
        report.finish()
        text = report.summary_text()
        assert "Errors: 1" in text
        assert "intake" in text

    def test_summary_text_many_errors_truncated(self):
        report = PipelineReport()
        for i in range(8):
            report.add_error("stage", f"error {i}")
        text = report.summary_text()
        assert "... and 3 more" in text

    def test_to_notification_payload(self):
        report = PipelineReport()
        report.mark_stage_complete("journal")
        report.outputs_written = ["a.md"]
        payload = report.to_notification_payload()
        assert payload["status"] == "success"
        assert payload["outputs"] == 1
        assert "journal" in payload["stages"]


class TestSaveLoadReport:
    def test_save_and_load(self, tmp_path):
        report = PipelineReport()
        report.mark_stage_complete("journal")
        report.add_error("intake", "test error")
        report.finish()

        save_report(report, tmp_path)
        loaded = load_report(tmp_path)

        assert loaded is not None
        assert loaded.stages_completed == ["journal"]
        assert loaded.error_count == 1

    def test_load_nonexistent(self, tmp_path):
        assert load_report(tmp_path) is None

    def test_load_corrupt(self, tmp_path):
        (tmp_path / ".distill-last-run.json").write_text("not json")
        assert load_report(tmp_path) is None
