"""Unit and property-based tests for PytestRunner (Layer 6 — Validation).

Covers PytestRunner.run() (mocked subprocess) and PytestRunner._parse_counts(),
plus Property 20 (pytest portion): Validator output parsing round-trip.

**Validates: Requirements 6.4**
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.validation.exceptions import ValidationTimeoutError
from local_sage.validation.pytest_runner import PytestRunner
from local_sage.validation.result import PytestCounts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(stdout: str, returncode: int = 0) -> MagicMock:
    """Return a mock CompletedProcess with the given stdout.

    Args:
        stdout: The stdout string to return.
        returncode: The process return code.

    Returns:
        A MagicMock configured to look like subprocess.CompletedProcess.
    """
    mock = MagicMock()
    mock.stdout = stdout
    mock.returncode = returncode
    return mock


def _make_json_report(passed: int, failed: int, error: int) -> str:
    """Build a minimal pytest JSON report string.

    Args:
        passed: Number of passed tests.
        failed: Number of failed tests.
        error: Number of errored tests.

    Returns:
        A JSON string matching the pytest-json-report format.
    """
    report = {"summary": {"passed": passed, "failed": failed, "error": error}}
    return json.dumps(report)


# ---------------------------------------------------------------------------
# Unit tests — _parse_counts()
# ---------------------------------------------------------------------------


class TestParseCounts:
    """Unit tests for PytestRunner._parse_counts()."""

    def test_parse_counts_extracts_passed_failed_errors(self) -> None:
        """_parse_counts() correctly extracts passed, failed, and error counts."""
        runner = PytestRunner()
        stdout = _make_json_report(passed=10, failed=2, error=1)
        counts = runner._parse_counts(stdout)
        assert counts.passed == 10
        assert counts.failed == 2
        assert counts.errors == 1

    def test_parse_counts_returns_zeros_on_empty_stdout(self) -> None:
        """_parse_counts() returns PytestCounts(0, 0, 0) when stdout is empty."""
        runner = PytestRunner()
        counts = runner._parse_counts("")
        assert counts == PytestCounts(passed=0, failed=0, errors=0)

    def test_parse_counts_returns_zeros_on_invalid_json(self) -> None:
        """_parse_counts() returns PytestCounts(0, 0, 0) when JSON is malformed."""
        runner = PytestRunner()
        counts = runner._parse_counts("not json at all")
        assert counts == PytestCounts(passed=0, failed=0, errors=0)

    def test_parse_counts_handles_missing_summary_keys(self) -> None:
        """_parse_counts() defaults missing summary keys to 0."""
        runner = PytestRunner()
        stdout = json.dumps({"summary": {"passed": 3}})
        counts = runner._parse_counts(stdout)
        assert counts.passed == 3
        assert counts.failed == 0
        assert counts.errors == 0

    def test_parse_counts_skips_non_json_prefix(self) -> None:
        """_parse_counts() finds JSON even when non-JSON text precedes it."""
        runner = PytestRunner()
        prefix = "some pytest output\n"
        json_part = _make_json_report(passed=5, failed=0, error=0)
        counts = runner._parse_counts(prefix + json_part)
        assert counts.passed == 5

    def test_parse_counts_returns_pytest_counts_instance(self) -> None:
        """_parse_counts() always returns a PytestCounts instance."""
        runner = PytestRunner()
        result = runner._parse_counts(_make_json_report(1, 0, 0))
        assert isinstance(result, PytestCounts)


# ---------------------------------------------------------------------------
# Unit tests — run() with mocked subprocess
# ---------------------------------------------------------------------------


class TestPytestRunnerRun:
    """Unit tests for PytestRunner.run() with mocked subprocess."""

    def test_run_returns_pytest_counts_on_success(self, tmp_path: Path) -> None:
        """run() returns PytestCounts parsed from subprocess stdout."""
        stdout = _make_json_report(passed=7, failed=0, error=0)
        mock_result = _make_completed_process(stdout=stdout, returncode=0)

        with patch("local_sage.validation.pytest_runner.subprocess.run", return_value=mock_result):
            runner = PytestRunner()
            counts = runner.run(tmp_path)

        assert counts.passed == 7
        assert counts.failed == 0
        assert counts.errors == 0

    def test_run_returns_counts_even_on_nonzero_exit(self, tmp_path: Path) -> None:
        """run() returns PytestCounts even when pytest exits with non-zero code."""
        stdout = _make_json_report(passed=3, failed=2, error=0)
        mock_result = _make_completed_process(stdout=stdout, returncode=1)

        with patch("local_sage.validation.pytest_runner.subprocess.run", return_value=mock_result):
            runner = PytestRunner()
            counts = runner.run(tmp_path)

        assert counts.failed == 2

    def test_run_raises_validation_timeout_error_on_timeout(self, tmp_path: Path) -> None:
        """run() raises ValidationTimeoutError when subprocess times out."""
        with patch(
            "local_sage.validation.pytest_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=60),
        ):
            runner = PytestRunner()
            with pytest.raises(ValidationTimeoutError) as exc_info:
                runner.run(tmp_path, timeout=60)

        assert exc_info.value.tool == "pytest"
        assert exc_info.value.timeout_seconds == 60

    def test_run_passes_cwd_to_subprocess(self, tmp_path: Path) -> None:
        """run() passes repo_dir as cwd to subprocess.run."""
        stdout = _make_json_report(passed=1, failed=0, error=0)
        mock_result = _make_completed_process(stdout=stdout)

        with patch(
            "local_sage.validation.pytest_runner.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            runner = PytestRunner()
            runner.run(tmp_path)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == tmp_path

    def test_run_passes_timeout_to_subprocess(self, tmp_path: Path) -> None:
        """run() passes the timeout parameter to subprocess.run."""
        stdout = _make_json_report(passed=1, failed=0, error=0)
        mock_result = _make_completed_process(stdout=stdout)

        with patch(
            "local_sage.validation.pytest_runner.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            runner = PytestRunner()
            runner.run(tmp_path, timeout=30)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 30


# ---------------------------------------------------------------------------
# Property 20 (pytest portion): Validator output parsing round-trip
# ---------------------------------------------------------------------------


@given(
    passed=st.integers(min_value=0, max_value=100),
    failed=st.integers(min_value=0, max_value=100),
    error=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=100)
def test_property_20_pytest_parsing_round_trip(passed: int, failed: int, error: int) -> None:
    """Property 20 (pytest): Validator output parsing round-trip.

    For any valid pytest JSON report with known passed, failed, error counts,
    PytestRunner SHALL return a PytestCounts with matching values.

    # Feature: local-sage, Property 20: Validator output parsing round-trip (pytest)
    **Validates: Requirements 6.4**
    """
    # Feature: local-sage, Property 20: Validator output parsing round-trip (pytest)
    report = {"summary": {"passed": passed, "failed": failed, "error": error}}
    stdout = json.dumps(report)

    mock_result = _make_completed_process(stdout=stdout, returncode=0 if failed == 0 else 1)

    with patch(
        "local_sage.validation.pytest_runner.subprocess.run",
        return_value=mock_result,
    ):
        runner = PytestRunner()
        counts = runner.run(Path("/fake/repo"))

    assert counts.passed == passed
    assert counts.failed == failed
    assert counts.errors == error
