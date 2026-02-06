"""Tests pass KPI measurer.

Runs the project test suite and reports the percentage of tests passing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from session_insights.measurers.base import KPIResult, Measurer

# Derive the project root (two levels up from this file: src/session_insights/measurers/)
_PROJECT_ROOT = Path(__file__).parents[3]


class TestsPassMeasurer(Measurer):
    """Measures percentage of tests passing in the project test suite."""

    KPI_NAME = "tests_pass"
    TARGET = 100.0

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or _PROJECT_ROOT

    def measure(self) -> KPIResult:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/",
                    "-q",
                    "--tb=no",
                    "-o",
                    "addopts=",
                ],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "test suite timed out"},
            )
        except Exception as e:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": str(e)},
            )

        return self._parse_results(result.stdout, result.stderr, result.returncode)

    def _parse_results(
        self, stdout: str, stderr: str, returncode: int
    ) -> KPIResult:
        """Parse pytest output to extract pass/fail counts."""
        output = stdout + "\n" + stderr

        # Try to parse the summary line like "459 passed" or "458 passed, 1 failed"
        passed = 0
        failed = 0
        errors = 0

        passed_match = re.search(r"(\d+) passed", output)
        if passed_match:
            passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            failed = int(failed_match.group(1))

        errors_match = re.search(r"(\d+) error", output)
        if errors_match:
            errors = int(errors_match.group(1))

        total = passed + failed + errors
        value = (passed / total * 100) if total > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "returncode": returncode,
            },
        )


if __name__ == "__main__":
    result = TestsPassMeasurer().measure()
    print(result.to_json())
