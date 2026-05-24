"""Pytest subprocess runner for Layer 6 — Validation.

Provides :class:`PytestRunner`, which invokes pytest as a subprocess with
JSON reporting and parses the output into a :class:`~local_sage.validation.result.PytestCounts`
dataclass.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from local_sage.validation.exceptions import ValidationTimeoutError
from local_sage.validation.result import PytestCounts

logger = logging.getLogger(__name__)

_PYTEST_CMD = [
    sys.executable,
    "-m",
    "pytest",
    "--tb=short",
    "--json-report",
    "--json-report-file=-",
    "-q",
]


class PytestRunner:
    """Runs pytest as a subprocess and returns structured pass/fail counts.

    Uses ``pytest-json-report`` to capture structured output via stdout
    (``--json-report-file=-``).  A non-zero exit code is expected when
    tests fail and is handled gracefully — only a timeout raises an
    exception.

    Example::

        runner = PytestRunner()
        counts = runner.run(Path("/path/to/repo"))
        print(counts.failed)  # number of failing tests
    """

    def run(self, repo_dir: Path, timeout: int = 60) -> PytestCounts:
        """Run pytest in *repo_dir* and return pass/fail/error counts.

        Invokes ``python -m pytest --tb=short --json-report
        --json-report-file=- -q`` as a subprocess.  The JSON report is
        written to stdout and parsed to extract summary counts.

        Args:
            repo_dir: Path to the repository root to run pytest in.
            timeout: Maximum seconds to wait for pytest to complete.

        Returns:
            A :class:`~local_sage.validation.result.PytestCounts` with
            ``passed``, ``failed``, and ``errors`` counts.

        Raises:
            ValidationTimeoutError: If pytest does not complete within
                *timeout* seconds.
        """
        try:
            result = subprocess.run(
                _PYTEST_CMD,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ValidationTimeoutError(
                f"pytest timed out after {timeout} seconds",
                tool="pytest",
                timeout_seconds=timeout,
            ) from None

        return self._parse_counts(result.stdout)

    def _parse_counts(self, stdout: str) -> PytestCounts:
        """Parse the JSON report from pytest stdout into PytestCounts.

        Searches for the first ``{`` in stdout to locate the JSON payload,
        since pytest may emit non-JSON lines before the report.  Falls back
        to zero counts if the JSON cannot be parsed.

        Args:
            stdout: Raw stdout string from the pytest subprocess.

        Returns:
            A :class:`~local_sage.validation.result.PytestCounts` instance.
        """
        json_start = stdout.find("{")
        if json_start == -1:
            logger.warning("No JSON found in pytest output; returning zero counts")
            return PytestCounts(passed=0, failed=0, errors=0)

        try:
            report = json.loads(stdout[json_start:])
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse pytest JSON report: %s", exc)
            return PytestCounts(passed=0, failed=0, errors=0)

        summary = report.get("summary", {})
        return PytestCounts(
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            errors=summary.get("error", 0),
        )
