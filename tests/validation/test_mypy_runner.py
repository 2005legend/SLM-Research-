"""Unit and property-based tests for MypyRunner (Layer 6 — Validation).

Covers MypyRunner.run() (mocked subprocess) and MypyRunner._parse_errors(),
plus Property 20 (mypy portion): Validator output parsing round-trip.

**Validates: Requirements 6.5**
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.validation.exceptions import ValidationTimeoutError
from local_sage.validation.mypy_runner import MypyRunner
from local_sage.validation.result import MypyError

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


def _make_mypy_line(file: str, line: int, col: int, msg: str, code: str) -> str:
    """Build a single mypy error output line.

    Args:
        file: File path string.
        line: Line number.
        col: Column number.
        msg: Error message.
        code: Mypy error code.

    Returns:
        A formatted mypy error line.
    """
    return f"{file}:{line}:{col}: error: {msg} [{code}]"


# ---------------------------------------------------------------------------
# Unit tests — _parse_errors()
# ---------------------------------------------------------------------------


class TestParseErrors:
    """Unit tests for MypyRunner._parse_errors()."""

    def test_parse_errors_returns_empty_list_for_empty_stdout(self) -> None:
        """_parse_errors() returns [] when stdout is empty."""
        runner = MypyRunner()
        assert runner._parse_errors("") == []

    def test_parse_errors_parses_single_error_line(self) -> None:
        """_parse_errors() correctly parses a single mypy error line."""
        runner = MypyRunner()
        line = _make_mypy_line(
            "local_sage/model/client.py", 42, 8, "Incompatible return value", "return-value"
        )
        errors = runner._parse_errors(line)
        assert len(errors) == 1
        err = errors[0]
        assert err.file_path == Path("local_sage/model/client.py")
        assert err.line == 42
        assert err.column == 8
        assert err.message == "Incompatible return value"
        assert err.error_code == "return-value"

    def test_parse_errors_parses_multiple_error_lines(self) -> None:
        """_parse_errors() parses multiple error lines from stdout."""
        runner = MypyRunner()
        stdout = "\n".join(
            [
                _make_mypy_line("a.py", 1, 1, "error one", "misc"),
                _make_mypy_line("b.py", 2, 4, "error two", "arg-type"),
            ]
        )
        errors = runner._parse_errors(stdout)
        assert len(errors) == 2

    def test_parse_errors_skips_non_error_lines(self) -> None:
        """_parse_errors() skips lines that do not match the error pattern."""
        runner = MypyRunner()
        stdout = (
            "Found 2 errors in 1 file (checked 5 source files)\n"
            + _make_mypy_line("a.py", 5, 1, "some error", "misc")
            + "\nSuccess: no issues found"
        )
        errors = runner._parse_errors(stdout)
        assert len(errors) == 1

    def test_parse_errors_returns_mypy_error_instances(self) -> None:
        """_parse_errors() returns MypyError dataclass instances."""
        runner = MypyRunner()
        line = _make_mypy_line("foo.py", 1, 1, "msg", "code")
        errors = runner._parse_errors(line)
        assert all(isinstance(e, MypyError) for e in errors)

    def test_parse_errors_file_path_is_path_object(self) -> None:
        """_parse_errors() returns MypyError with file_path as a Path object."""
        runner = MypyRunner()
        line = _make_mypy_line("local_sage/foo.py", 1, 1, "msg", "code")
        errors = runner._parse_errors(line)
        assert isinstance(errors[0].file_path, Path)

    def test_parse_errors_skips_warning_lines(self) -> None:
        """_parse_errors() skips mypy warning lines (not 'error:')."""
        runner = MypyRunner()
        stdout = "local_sage/foo.py:1:1: note: some note\n"
        errors = runner._parse_errors(stdout)
        assert errors == []


# ---------------------------------------------------------------------------
# Unit tests — run() with mocked subprocess
# ---------------------------------------------------------------------------


class TestMypyRunnerRun:
    """Unit tests for MypyRunner.run() with mocked subprocess."""

    def test_run_returns_empty_list_on_clean_output(self, tmp_path: Path) -> None:
        """run() returns [] when mypy produces no error lines."""
        mock_result = _make_completed_process(stdout="Success: no issues found\n")

        with patch("local_sage.validation.mypy_runner.subprocess.run", return_value=mock_result):
            runner = MypyRunner()
            errors = runner.run(tmp_path)

        assert errors == []

    def test_run_returns_errors_on_mypy_output(self, tmp_path: Path) -> None:
        """run() returns MypyError objects parsed from subprocess stdout."""
        line = _make_mypy_line("local_sage/foo.py", 10, 4, "bad type", "arg-type")
        mock_result = _make_completed_process(stdout=line + "\n", returncode=1)

        with patch("local_sage.validation.mypy_runner.subprocess.run", return_value=mock_result):
            runner = MypyRunner()
            errors = runner.run(tmp_path)

        assert len(errors) == 1
        assert errors[0].error_code == "arg-type"

    def test_run_raises_validation_timeout_error_on_timeout(self, tmp_path: Path) -> None:
        """run() raises ValidationTimeoutError when subprocess times out."""
        with patch(
            "local_sage.validation.mypy_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="mypy", timeout=60),
        ):
            runner = MypyRunner()
            with pytest.raises(ValidationTimeoutError) as exc_info:
                runner.run(tmp_path, timeout=60)

        assert exc_info.value.tool == "mypy"
        assert exc_info.value.timeout_seconds == 60

    def test_run_passes_cwd_to_subprocess(self, tmp_path: Path) -> None:
        """run() passes repo_dir as cwd to subprocess.run."""
        mock_result = _make_completed_process(stdout="")

        with patch(
            "local_sage.validation.mypy_runner.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            runner = MypyRunner()
            runner.run(tmp_path)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == tmp_path

    def test_run_passes_timeout_to_subprocess(self, tmp_path: Path) -> None:
        """run() passes the timeout parameter to subprocess.run."""
        mock_result = _make_completed_process(stdout="")

        with patch(
            "local_sage.validation.mypy_runner.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            runner = MypyRunner()
            runner.run(tmp_path, timeout=45)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 45


# ---------------------------------------------------------------------------
# Property 20 (mypy portion): Validator output parsing round-trip
# ---------------------------------------------------------------------------


@given(
    file=st.from_regex(r"[a-z][a-z0-9_/]+\.py", fullmatch=True),
    line=st.integers(min_value=1, max_value=9999),
    col=st.integers(min_value=1, max_value=999),
    msg=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
            whitelist_characters=" _-.",
        ),
        min_size=1,
        max_size=60,
    ).filter(lambda s: "[" not in s and "]" not in s and s.strip()),
    code=st.from_regex(r"[a-z][a-z0-9-]{1,30}", fullmatch=True),
)
@settings(max_examples=100)
def test_property_20_mypy_parsing_round_trip(
    file: str, line: int, col: int, msg: str, code: str
) -> None:
    """Property 20 (mypy): Validator output parsing round-trip.

    For any mypy output line matching <file>:<line>:<col>: error: <msg> [<code>],
    MypyRunner SHALL return a MypyError with matching file_path, line, column,
    error_code, and message.

    # Feature: local-sage, Property 20: Validator output parsing round-trip (mypy)
    **Validates: Requirements 6.5**
    """
    # Feature: local-sage, Property 20: Validator output parsing round-trip (mypy)
    mypy_line = _make_mypy_line(file, line, col, msg, code)
    runner = MypyRunner()
    errors = runner._parse_errors(mypy_line)

    assert len(errors) == 1
    err = errors[0]
    assert err.file_path == Path(file)
    assert err.line == line
    assert err.column == col
    assert err.message == msg
    assert err.error_code == code
