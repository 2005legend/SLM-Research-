"""Unit and property-based tests for RuffRunner (Layer 6 — Validation).

Covers RuffRunner.run(), _run_check(), _run_format_check(), and
_parse_check_output(), plus Property 20 (ruff portion): Validator output
parsing round-trip.

**Validates: Requirements 6.6**
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
from local_sage.validation.result import RuffViolation
from local_sage.validation.ruff_runner import RuffRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Return a mock CompletedProcess with the given stdout and returncode.

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


def _make_ruff_json(filename: str, row: int, column: int, code: str, message: str) -> str:
    """Build a ruff check JSON output string with a single violation.

    Args:
        filename: File path string.
        row: Line number.
        column: Column number.
        code: Ruff rule code.
        message: Violation message.

    Returns:
        A JSON string matching the ruff --output-format=json format.
    """
    violations = [
        {
            "filename": filename,
            "location": {"row": row, "column": column},
            "code": code,
            "message": message,
        }
    ]
    return json.dumps(violations)


# ---------------------------------------------------------------------------
# Unit tests — _parse_check_output()
# ---------------------------------------------------------------------------


class TestParseCheckOutput:
    """Unit tests for RuffRunner._parse_check_output()."""

    def test_parse_check_output_returns_empty_list_for_empty_stdout(self) -> None:
        """_parse_check_output() returns [] when stdout is empty."""
        runner = RuffRunner()
        assert runner._parse_check_output("") == []

    def test_parse_check_output_returns_empty_list_for_whitespace(self) -> None:
        """_parse_check_output() returns [] when stdout is only whitespace."""
        runner = RuffRunner()
        assert runner._parse_check_output("   \n  ") == []

    def test_parse_check_output_parses_single_violation(self) -> None:
        """_parse_check_output() correctly parses a single ruff violation."""
        runner = RuffRunner()
        stdout = _make_ruff_json("local_sage/foo.py", 10, 5, "E501", "Line too long")
        violations = runner._parse_check_output(stdout)
        assert len(violations) == 1
        v = violations[0]
        assert v.file_path == Path("local_sage/foo.py")
        assert v.line == 10
        assert v.column == 5
        assert v.rule_code == "E501"
        assert v.message == "Line too long"

    def test_parse_check_output_parses_multiple_violations(self) -> None:
        """_parse_check_output() parses multiple violations from JSON array."""
        runner = RuffRunner()
        raw = [
            {
                "filename": "a.py",
                "location": {"row": 1, "column": 1},
                "code": "E501",
                "message": "line too long",
            },
            {
                "filename": "b.py",
                "location": {"row": 5, "column": 3},
                "code": "F401",
                "message": "unused import",
            },
        ]
        violations = runner._parse_check_output(json.dumps(raw))
        assert len(violations) == 2

    def test_parse_check_output_returns_ruff_violation_instances(self) -> None:
        """_parse_check_output() returns RuffViolation dataclass instances."""
        runner = RuffRunner()
        stdout = _make_ruff_json("a.py", 1, 1, "E501", "msg")
        violations = runner._parse_check_output(stdout)
        assert all(isinstance(v, RuffViolation) for v in violations)

    def test_parse_check_output_returns_empty_on_invalid_json(self) -> None:
        """_parse_check_output() returns [] when stdout is not valid JSON."""
        runner = RuffRunner()
        violations = runner._parse_check_output("not json")
        assert violations == []

    def test_parse_check_output_file_path_is_path_object(self) -> None:
        """_parse_check_output() returns RuffViolation with file_path as Path."""
        runner = RuffRunner()
        stdout = _make_ruff_json("local_sage/bar.py", 1, 1, "E501", "msg")
        violations = runner._parse_check_output(stdout)
        assert isinstance(violations[0].file_path, Path)


# ---------------------------------------------------------------------------
# Unit tests — run() with mocked subprocess
# ---------------------------------------------------------------------------


class TestRuffRunnerRun:
    """Unit tests for RuffRunner.run() with mocked subprocess."""

    def test_run_returns_empty_list_when_no_violations(self, tmp_path: Path) -> None:
        """run() returns [] when ruff check and format both pass."""
        clean_check = _make_completed_process(stdout="[]", returncode=0)
        clean_format = _make_completed_process(stdout="", returncode=0)

        with patch(
            "local_sage.validation.ruff_runner.subprocess.run",
            side_effect=[clean_check, clean_format],
        ):
            runner = RuffRunner()
            violations = runner.run(tmp_path)

        assert violations == []

    def test_run_returns_lint_violations_from_check(self, tmp_path: Path) -> None:
        """run() returns lint violations from ruff check output."""
        check_stdout = _make_ruff_json("a.py", 1, 1, "E501", "line too long")
        check_result = _make_completed_process(stdout=check_stdout, returncode=1)
        format_result = _make_completed_process(stdout="", returncode=0)

        with patch(
            "local_sage.validation.ruff_runner.subprocess.run",
            side_effect=[check_result, format_result],
        ):
            runner = RuffRunner()
            violations = runner.run(tmp_path)

        assert len(violations) == 1
        assert violations[0].rule_code == "E501"

    def test_run_appends_format_violation_on_format_failure(self, tmp_path: Path) -> None:
        """run() appends a FORMAT violation when ruff format --check fails."""
        check_result = _make_completed_process(stdout="[]", returncode=0)
        format_result = _make_completed_process(stdout="", returncode=1)

        with patch(
            "local_sage.validation.ruff_runner.subprocess.run",
            side_effect=[check_result, format_result],
        ):
            runner = RuffRunner()
            violations = runner.run(tmp_path)

        assert len(violations) == 1
        assert violations[0].rule_code == "FORMAT"

    def test_run_raises_validation_timeout_error_on_check_timeout(self, tmp_path: Path) -> None:
        """run() raises ValidationTimeoutError when ruff check times out."""
        with patch(
            "local_sage.validation.ruff_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ruff", timeout=30),
        ):
            runner = RuffRunner()
            with pytest.raises(ValidationTimeoutError) as exc_info:
                runner.run(tmp_path, timeout=30)

        assert exc_info.value.tool == "ruff"
        assert exc_info.value.timeout_seconds == 30

    def test_run_raises_validation_timeout_error_on_format_timeout(self, tmp_path: Path) -> None:
        """run() raises ValidationTimeoutError when ruff format --check times out."""
        check_result = _make_completed_process(stdout="[]", returncode=0)

        with patch(
            "local_sage.validation.ruff_runner.subprocess.run",
            side_effect=[
                check_result,
                subprocess.TimeoutExpired(cmd="ruff", timeout=30),
            ],
        ):
            runner = RuffRunner()
            with pytest.raises(ValidationTimeoutError) as exc_info:
                runner.run(tmp_path, timeout=30)

        assert exc_info.value.tool == "ruff"


# ---------------------------------------------------------------------------
# Property 20 (ruff portion): Validator output parsing round-trip
# ---------------------------------------------------------------------------


@given(
    filename=st.from_regex(r"[a-z][a-z0-9_/]+\.py", fullmatch=True),
    row=st.integers(min_value=1, max_value=9999),
    column=st.integers(min_value=1, max_value=999),
    code=st.from_regex(r"[A-Z][0-9]{3}", fullmatch=True),
    message=st.text(
        alphabet=st.characters(
            blacklist_characters="\n\r",
            blacklist_categories=("Cs",),
        ),
        min_size=1,
        max_size=80,
    ),
)
@settings(max_examples=100)
def test_property_20_ruff_parsing_round_trip(
    filename: str, row: int, column: int, code: str, message: str
) -> None:
    """Property 20 (ruff): Validator output parsing round-trip.

    For any ruff JSON output with known violations, RuffRunner SHALL return
    RuffViolation objects with matching fields.

    # Feature: local-sage, Property 20: Validator output parsing round-trip (ruff)
    **Validates: Requirements 6.6**
    """
    # Feature: local-sage, Property 20: Validator output parsing round-trip (ruff)
    stdout = _make_ruff_json(filename, row, column, code, message)
    runner = RuffRunner()
    violations = runner._parse_check_output(stdout)

    assert len(violations) == 1
    v = violations[0]
    assert v.file_path == Path(filename)
    assert v.line == row
    assert v.column == column
    assert v.rule_code == code
    assert v.message == message
