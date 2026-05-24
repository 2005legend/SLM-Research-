"""Mypy subprocess runner for Layer 6 — Validation.

Provides :class:`MypyRunner`, which invokes mypy as a subprocess and
parses its stdout into a list of :class:`~local_sage.validation.result.MypyError`
dataclasses.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

from local_sage.validation.exceptions import ValidationTimeoutError
from local_sage.validation.result import MypyError

logger = logging.getLogger(__name__)

_MYPY_CMD = [
    sys.executable,
    "-m",
    "mypy",
    "local_sage/",
    "--show-column-numbers",
    "--no-error-summary",
]

# Matches lines like: local_sage/foo.py:10:4: error: some message [error-code]
_ERROR_RE = re.compile(
    r"^(?P<file>.+):(?P<line>\d+):(?P<col>\d+): error: (?P<msg>.+) \[(?P<code>[^\]]+)\]$"
)


class MypyRunner:
    """Runs mypy as a subprocess and returns a list of type errors.

    Invokes ``python -m mypy local_sage/ --show-column-numbers
    --no-error-summary`` and parses each output line with a regex.
    Lines that do not match the error pattern (notes, warnings, summary
    lines) are silently skipped.

    Example::

        runner = MypyRunner()
        errors = runner.run(Path("/path/to/repo"))
        for err in errors:
            print(err.file_path, err.line, err.message)
    """

    def run(self, repo_dir: Path, timeout: int = 60) -> list[MypyError]:
        """Run mypy in *repo_dir* and return a list of type errors.

        Invokes ``python -m mypy local_sage/ --show-column-numbers
        --no-error-summary`` as a subprocess.  Only lines matching the
        ``<file>:<line>:<col>: error: <msg> [<code>]`` pattern are
        returned; all other output is ignored.

        Args:
            repo_dir: Path to the repository root to run mypy in.
            timeout: Maximum seconds to wait for mypy to complete.

        Returns:
            A list of :class:`~local_sage.validation.result.MypyError`
            objects, one per matched error line.  An empty list means no
            errors were found.

        Raises:
            ValidationTimeoutError: If mypy does not complete within
                *timeout* seconds.
        """
        try:
            result = subprocess.run(
                _MYPY_CMD,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ValidationTimeoutError(
                f"mypy timed out after {timeout} seconds",
                tool="mypy",
                timeout_seconds=timeout,
            ) from None

        return self._parse_errors(result.stdout)

    def _parse_errors(self, stdout: str) -> list[MypyError]:
        """Parse mypy stdout lines into MypyError objects.

        Iterates over each line and applies the error regex.  Lines that
        do not match (notes, warnings, blank lines, summary) are skipped.

        Args:
            stdout: Raw stdout string from the mypy subprocess.

        Returns:
            A list of :class:`~local_sage.validation.result.MypyError`
            instances for every matched error line.
        """
        errors: list[MypyError] = []
        for line in stdout.splitlines():
            match = _ERROR_RE.match(line.strip())
            if match is None:
                continue
            errors.append(
                MypyError(
                    file_path=Path(match.group("file")),
                    line=int(match.group("line")),
                    column=int(match.group("col")),
                    error_code=match.group("code"),
                    message=match.group("msg"),
                )
            )
        return errors
