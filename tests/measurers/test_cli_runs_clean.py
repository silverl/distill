"""Tests for cli_runs_clean KPI measurer."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from session_insights.measurers.base import KPIResult
from session_insights.measurers.cli_runs_clean import (
    CLIRunsCleanMeasurer,
    _build_test_matrix,
    _create_malformed_claude_dir,
    _create_valid_claude_dir,
    _create_valid_vermas_dir,
)


class TestCLIRunsCleanMeasurer:
    """Tests for the cli_runs_clean measurer."""

    def test_result_is_kpi_result(self) -> None:
        """Measurer returns a KPIResult with correct KPI name."""
        measurer = CLIRunsCleanMeasurer()
        result = measurer.measure()
        assert isinstance(result, KPIResult)
        assert result.kpi == "cli_runs_clean"
        assert result.target == 100.0

    def test_value_in_range(self) -> None:
        """Measured value is between 0 and 100."""
        measurer = CLIRunsCleanMeasurer()
        result = measurer.measure()
        assert 0.0 <= result.value <= 100.0

    def test_details_contain_run_info(self) -> None:
        """Details include total_runs, clean_runs, and failures list."""
        measurer = CLIRunsCleanMeasurer()
        result = measurer.measure()
        assert "total_runs" in result.details
        assert "clean_runs" in result.details
        assert "failures" in result.details
        assert isinstance(result.details["failures"], list)
        assert result.details["total_runs"] > 0

    def test_json_serialization(self) -> None:
        """Result serializes to valid JSON."""
        measurer = CLIRunsCleanMeasurer()
        result = measurer.measure()
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["kpi"] == "cli_runs_clean"
        assert isinstance(parsed["value"], float)


class TestTestMatrix:
    """Tests for the test matrix builder."""

    def test_matrix_has_entries(self) -> None:
        """Test matrix produces a non-empty list of scenarios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            matrix = _build_test_matrix(base)
            assert len(matrix) >= 10

    def test_matrix_entries_are_tuples(self) -> None:
        """Each matrix entry is a (args, exit_code, description) tuple."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            matrix = _build_test_matrix(base)
            for args, code, desc in matrix:
                assert isinstance(args, list)
                assert isinstance(code, int)
                assert isinstance(desc, str)


class TestDataCreators:
    """Tests for test data creation helpers."""

    def test_create_valid_claude_dir(self) -> None:
        """Valid Claude dir creates expected structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _create_valid_claude_dir(base)
            session_file = base / ".claude" / "projects" / "test-project" / "session.jsonl"
            assert session_file.exists()
            lines = session_file.read_text().strip().split("\n")
            assert len(lines) >= 2
            for line in lines:
                json.loads(line)  # Should not raise

    def test_create_malformed_claude_dir(self) -> None:
        """Malformed Claude dir creates file with invalid JSON lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _create_malformed_claude_dir(base)
            session_file = base / ".claude" / "projects" / "bad-project" / "session.jsonl"
            assert session_file.exists()
            lines = session_file.read_text().strip().split("\n")
            assert len(lines) >= 3
            # At least one line should be malformed
            bad_count = 0
            for line in lines:
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    bad_count += 1
            assert bad_count >= 1

    def test_create_valid_vermas_dir(self) -> None:
        """Valid VerMAS dir creates expected structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _create_valid_vermas_dir(base)
            signals_dir = (
                base
                / ".vermas"
                / "state"
                / "mission-test-cycle-1-execute-sample-task"
                / "signals"
            )
            assert signals_dir.exists()
            assert len(list(signals_dir.glob("*.yaml"))) >= 1


class TestMeasurerWithMockedSubprocess:
    """Tests that verify measurer behavior with controlled subprocess results."""

    def test_all_clean_gives_100(self) -> None:
        """When all runs succeed, value should be 100."""
        measurer = CLIRunsCleanMeasurer()

        # Build matrix and run with a mock that always returns expected code
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            matrix = _build_test_matrix(base)

            # Create mock results matching expected codes
            mock_results = []
            for args, expected_code, desc in matrix:
                mock_result = subprocess.CompletedProcess(
                    args=args, returncode=expected_code, stdout="", stderr=""
                )
                mock_results.append(mock_result)

            with patch(
                "session_insights.measurers.cli_runs_clean._run_cli",
                side_effect=mock_results,
            ):
                result = measurer._run_matrix(matrix, base)

        assert result.value == 100.0
        assert result.details["failures"] == []

    def test_timeout_counted_as_failure(self) -> None:
        """Subprocess timeout should count as a failure."""
        measurer = CLIRunsCleanMeasurer()

        matrix: list[tuple[list[str], int, str]] = [
            (["--help"], 0, "help"),
        ]

        with patch(
            "session_insights.measurers.cli_runs_clean._run_cli",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=30),
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = measurer._run_matrix(matrix, Path(tmpdir))

        assert result.value == 0.0
        assert len(result.details["failures"]) == 1
        assert result.details["failures"][0]["error"] == "timeout"
