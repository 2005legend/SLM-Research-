"""Pytest subprocess runner for Layer 6 — Validation.

Provides :class:`PytestRunner`, which invokes pytest as a subprocess with
JSON reporting and parses the output into a :class:`~local_sage.validation.result.PytestCounts`
dataclass.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
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

    def run(self, repo_dir: Path, target_files: list[Path] | None = None, timeout: int = 60) -> PytestCounts:
        """Run pytest in *repo_dir* and return pass/fail/error counts.

        Invokes ``python -m pytest --tb=short --json-report
        --json-report-file=<tmpfile> -q`` as a subprocess.  The JSON report is
        written to a temporary file and parsed to extract summary counts.

        Args:
            repo_dir: Path to the repository root to run pytest in.
            target_files: Optional list of specific files to test.
            timeout: Maximum seconds to wait for pytest to complete.

        Returns:
            A :class:`~local_sage.validation.result.PytestCounts` with
            ``passed``, ``failed``, and ``errors`` counts.

        Raises:
            ValidationTimeoutError: If pytest does not complete within
                *timeout* seconds.
        """
        fd, report_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        paths: list[str] = []
        if target_files:
            for p in target_files:
                if p.name.startswith("test_") or p.name.endswith("_test.py") or "tests" in p.parts:
                    paths.append(str(p.absolute() if p.is_absolute() else p))
                else:
                    try:
                        if "local_sage" in p.parts:
                            idx = p.parts.index("local_sage")
                            test_path = repo_dir / "tests" / Path(*p.parts[idx+1:-1]) / f"test_{p.name}"
                        else:
                            test_path = repo_dir / "tests" / Path(*p.parts[:-1]) / f"test_{p.name}"
                            
                        if test_path.exists():
                            paths.append(str(test_path))
                    except ValueError:
                        pass
            
            # If target files were provided but none mapped to tests, skip running pytest
            if not paths:
                try:
                    os.remove(report_path)
                except OSError:
                    pass
                return PytestCounts(passed=0, failed=0, errors=0)

        cmd = _PYTEST_CMD + [f"--json-report-file={report_path}"] + (paths if paths else [])

        try:
            self._execute_pytest(cmd, repo_dir, timeout, report_path)
            return self._read_and_parse_report(report_path)
        finally:
            try:
                os.remove(report_path)
            except OSError:
                pass

    def _execute_pytest(self, cmd: list[str], repo_dir: Path, timeout: int, report_path: str) -> None:
        try:
            subprocess.run(
                cmd,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            try:
                os.remove(report_path)
            except OSError:
                pass
            raise ValidationTimeoutError(
                f"pytest timed out after {timeout} seconds",
                tool="pytest",
                timeout_seconds=timeout,
            ) from None

    def _read_and_parse_report(self, report_path: str) -> PytestCounts:
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self._parse_counts(content)
        except OSError:
            logger.warning("No JSON report file created by pytest; returning zero counts")
            return PytestCounts(passed=0, failed=0, errors=0)

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
