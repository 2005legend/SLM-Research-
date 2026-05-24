"""Ruff subprocess runner for Layer 6 — Validation.

Provides :class:`RuffRunner`, which invokes ruff as a subprocess for both
linting (``ruff check``) and format checking (``ruff format --check``),
then parses the results into a list of
:class:`~local_sage.validation.result.RuffViolation` dataclasses.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from local_sage.validation.exceptions import ValidationTimeoutError
from local_sage.validation.result import RuffViolation

logger = logging.getLogger(__name__)

_RUFF_CHECK_CMD = [sys.executable, "-m", "ruff", "check", "--output-format=json", "."]
_RUFF_FORMAT_CMD = [sys.executable, "-m", "ruff", "format", "--check", "."]

_FORMAT_VIOLATION_MESSAGE = "One or more files are not formatted correctly"


class RuffRunner:
    """Runs ruff lint and format checks as subprocesses.

    Makes two subprocess calls:

    1. ``ruff check --output-format=json .`` — parses the JSON array of
       lint violations.
    2. ``ruff format --check .`` — a non-zero exit code means at least one
       file is not formatted; this is reported as a single
       :class:`~local_sage.validation.result.RuffViolation` with
       ``rule_code="FORMAT"``.

    Example::

        runner = RuffRunner()
        violations = runner.run(Path("/path/to/repo"))
        for v in violations:
            print(v.rule_code, v.message)
    """

    def run(self, repo_dir: Path, timeout: int = 30) -> list[RuffViolation]:
        """Run ruff check and ruff format --check in *repo_dir*.

        Args:
            repo_dir: Path to the repository root to run ruff in.
            timeout: Maximum seconds to wait for each ruff subprocess.
                Applied independently to the check and format calls.

        Returns:
            A list of :class:`~local_sage.validation.result.RuffViolation`
            objects.  Lint violations come first, followed by a single
            ``FORMAT`` violation if formatting is not clean.  An empty
            list means no issues were found.

        Raises:
            ValidationTimeoutError: If either ruff subprocess does not
                complete within *timeout* seconds.
        """
        violations: list[RuffViolation] = []
        violations.extend(self._run_check(repo_dir, timeout))
        format_violation = self._run_format_check(repo_dir, timeout)
        if format_violation is not None:
            violations.append(format_violation)
        return violations

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_check(self, repo_dir: Path, timeout: int) -> list[RuffViolation]:
        """Run ``ruff check --output-format=json .`` and parse violations.

        Args:
            repo_dir: Repository root directory.
            timeout: Subprocess timeout in seconds.

        Returns:
            List of lint :class:`~local_sage.validation.result.RuffViolation`
            objects parsed from the JSON output.

        Raises:
            ValidationTimeoutError: If the subprocess times out.
        """
        try:
            result = subprocess.run(
                _RUFF_CHECK_CMD,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ValidationTimeoutError(
                f"ruff timed out after {timeout} seconds",
                tool="ruff",
                timeout_seconds=timeout,
            ) from None

        return self._parse_check_output(result.stdout)

    def _run_format_check(self, repo_dir: Path, timeout: int) -> RuffViolation | None:
        """Run ``ruff format --check .`` and return a violation if unformatted.

        Args:
            repo_dir: Repository root directory.
            timeout: Subprocess timeout in seconds.

        Returns:
            A FORMAT violation if any file is unformatted, else ``None``.

        Raises:
            ValidationTimeoutError: If the subprocess times out.
        """
        try:
            result = subprocess.run(
                _RUFF_FORMAT_CMD,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ValidationTimeoutError(
                f"ruff timed out after {timeout} seconds",
                tool="ruff",
                timeout_seconds=timeout,
            ) from None
        if result.returncode != 0:
            return RuffViolation(
                file_path=Path("."),
                line=0,
                column=0,
                rule_code="FORMAT",
                message=_FORMAT_VIOLATION_MESSAGE,
            )
        return None

    def _parse_check_output(self, stdout: str) -> list[RuffViolation]:
        """Parse the JSON array from ``ruff check --output-format=json``.

        Each element in the JSON array has ``filename``, ``location.row``,
        ``location.column``, ``code``, and ``message`` fields.

        Args:
            stdout: Raw stdout string from the ruff check subprocess.

        Returns:
            List of :class:`~local_sage.validation.result.RuffViolation`
            objects.  Returns an empty list if stdout is empty or cannot
            be parsed as JSON.
        """
        if not stdout.strip():
            return []

        try:
            raw_violations = json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse ruff JSON output: %s", exc)
            return []

        violations: list[RuffViolation] = []
        for item in raw_violations:
            location = item.get("location", {})
            violations.append(
                RuffViolation(
                    file_path=Path(item.get("filename", ".")),
                    line=location.get("row", 0),
                    column=location.get("column", 0),
                    rule_code=item.get("code", ""),
                    message=item.get("message", ""),
                )
            )
        return violations
