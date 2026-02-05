"""CLI runs clean KPI measurer.

Runs the session-insights CLI with a matrix of inputs and reports the
percentage of runs that exit cleanly (expected exit code).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from session_insights.measurers.base import KPIResult, Measurer

# Derive the src/ directory so subprocess can find session_insights
_SRC_DIR = str(Path(__file__).parents[2])


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the session-insights CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "session_insights", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": _SRC_DIR},
        timeout=30,
    )


def _create_valid_claude_dir(base: Path) -> None:
    """Create a .claude directory with valid session data."""
    project_dir = base / ".claude" / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    now = datetime.now()
    entries = [
        {
            "type": "user",
            "message": {"content": "Help me fix a bug"},
            "timestamp": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "type": "assistant",
            "message": {"content": "Sure, I will help."},
            "timestamp": (now - timedelta(minutes=55)).isoformat(),
        },
    ]
    session_file = project_dir / "session.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _create_malformed_claude_dir(base: Path) -> None:
    """Create a .claude directory with a mix of valid and malformed session data."""
    project_dir = base / ".claude" / "projects" / "bad-project"
    project_dir.mkdir(parents=True)

    now = datetime.now()
    session_file = project_dir / "session.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        # Valid entry
        f.write(
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": "hello"},
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                }
            )
            + "\n"
        )
        # Malformed line
        f.write("{{{not valid json\n")
        # Another valid entry
        f.write(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": "hi"},
                    "timestamp": now.isoformat(),
                }
            )
            + "\n"
        )


def _create_valid_vermas_dir(base: Path) -> None:
    """Create a .vermas directory with valid workflow data."""
    workflow_dir = base / ".vermas" / "state" / "mission-test-cycle-1-execute-sample-task"
    signals_dir = workflow_dir / "signals"
    signals_dir.mkdir(parents=True)

    signal_data = {
        "signal_id": "sig1",
        "agent_id": "dev01",
        "role": "dev",
        "signal": "done",
        "message": "Task completed",
        "workflow_id": "mission-test-cycle-1-execute-sample-task",
        "created_at": "2024-06-15T10:30:00",
    }
    (signals_dir / "sig1.yaml").write_text(yaml.dump(signal_data))


def _build_test_matrix(
    base_dir: Path,
) -> list[tuple[list[str], int, str]]:
    """Build a matrix of (cli_args, expected_exit_code, description) tuples."""
    output_dir = base_dir / "output"
    matrix: list[tuple[list[str], int, str]] = []

    # --- Valid directory scenarios ---
    valid_dir = base_dir / "valid"
    valid_dir.mkdir()
    _create_valid_claude_dir(valid_dir)

    matrix.append(
        (
            ["sessions", "--dir", str(valid_dir)],
            0,
            "sessions on valid dir",
        )
    )
    matrix.append(
        (
            ["analyze", "--dir", str(valid_dir), "--output", str(output_dir / "a")],
            0,
            "analyze on valid dir",
        )
    )

    # --- Empty directory (no sessions) ---
    empty_dir = base_dir / "empty"
    empty_dir.mkdir()

    matrix.append(
        (
            ["sessions", "--dir", str(empty_dir)],
            0,
            "sessions on empty dir",
        )
    )
    matrix.append(
        (
            ["analyze", "--dir", str(empty_dir), "--output", str(output_dir / "b")],
            0,
            "analyze on empty dir (no sessions found)",
        )
    )

    # --- Missing directory (typer should reject) ---
    missing = base_dir / "nonexistent"
    matrix.append(
        (
            ["sessions", "--dir", str(missing)],
            2,
            "sessions on missing dir",
        )
    )

    # --- --global flag ---
    matrix.append(
        (
            ["sessions", "--dir", str(valid_dir), "--global"],
            0,
            "sessions with --global",
        )
    )

    # --- Output to nested path ---
    matrix.append(
        (
            [
                "analyze",
                "--dir",
                str(valid_dir),
                "--output",
                str(output_dir / "nested" / "deep"),
            ],
            0,
            "analyze output to nested path",
        )
    )

    # --- Malformed sessions mixed with valid ---
    mixed_dir = base_dir / "mixed"
    mixed_dir.mkdir()
    _create_malformed_claude_dir(mixed_dir)

    matrix.append(
        (
            ["sessions", "--dir", str(mixed_dir)],
            0,
            "sessions on dir with malformed data",
        )
    )
    matrix.append(
        (
            ["analyze", "--dir", str(mixed_dir), "--output", str(output_dir / "c")],
            0,
            "analyze on dir with malformed data",
        )
    )

    # --- Invalid format ---
    matrix.append(
        (
            ["analyze", "--dir", str(valid_dir), "--format", "invalid"],
            1,
            "analyze with invalid format",
        )
    )

    # --- Help output ---
    matrix.append(
        (
            ["--help"],
            0,
            "help output",
        )
    )

    # --- VerMAS directory ---
    vermas_dir = base_dir / "vermas"
    vermas_dir.mkdir()
    _create_valid_vermas_dir(vermas_dir)

    matrix.append(
        (
            [
                "analyze",
                "--dir",
                str(vermas_dir),
                "--source",
                "vermas",
                "--output",
                str(output_dir / "d"),
            ],
            0,
            "analyze vermas source",
        )
    )

    return matrix


class CLIRunsCleanMeasurer(Measurer):
    """Measures percentage of CLI invocations that exit with expected code."""

    KPI_NAME = "cli_runs_clean"
    TARGET = 100.0

    def measure(self) -> KPIResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            matrix = _build_test_matrix(base)
            return self._run_matrix(matrix, base)

    def _run_matrix(
        self,
        matrix: list[tuple[list[str], int, str]],
        cwd: Path,
    ) -> KPIResult:
        total = len(matrix)
        clean = 0
        failures: list[dict[str, object]] = []

        for args, expected_code, description in matrix:
            try:
                result = _run_cli(*args, cwd=cwd)
                if result.returncode == expected_code:
                    clean += 1
                else:
                    failures.append(
                        {
                            "description": description,
                            "expected": expected_code,
                            "actual": result.returncode,
                            "stderr": result.stderr[:200],
                        }
                    )
            except subprocess.TimeoutExpired:
                failures.append(
                    {
                        "description": description,
                        "error": "timeout",
                    }
                )
            except Exception as e:
                failures.append(
                    {
                        "description": description,
                        "error": str(e),
                    }
                )

        value = (clean / total * 100) if total > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total_runs": total,
                "clean_runs": clean,
                "failures": failures,
            },
        )


if __name__ == "__main__":
    result = CLIRunsCleanMeasurer().measure()
    print(result.to_json())
