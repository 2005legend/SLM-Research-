"""Validation result dataclasses for Layer 6 — Validation.

These dataclasses represent the structured output of each validator
(pytest, mypy, ruff, contracts) and the aggregate ValidationResult
that is passed back to the orchestration layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PytestCounts:
    """Pass/fail/error counts from a pytest run.

    Attributes:
        passed: Number of tests that passed.
        failed: Number of tests that failed.
        errors: Number of tests that errored (collection or setup errors).
    """

    passed: int
    failed: int
    errors: int


@dataclass
class MypyError:
    """A single mypy type-checking error.

    Attributes:
        file_path: Path to the file containing the error.
        line: Line number of the error (1-indexed).
        column: Column number of the error (1-indexed).
        error_code: Mypy error code, e.g. ``"return-value"``.
        message: Human-readable error description.
    """

    file_path: Path
    line: int
    column: int
    error_code: str
    message: str


@dataclass
class RuffViolation:
    """A single ruff lint or format violation.

    Attributes:
        file_path: Path to the file containing the violation.
        line: Line number of the violation (1-indexed).
        column: Column number of the violation (1-indexed).
        rule_code: Ruff rule code, e.g. ``"E501"`` or ``"FORMAT"``.
        message: Human-readable violation description.
    """

    file_path: Path
    line: int
    column: int
    rule_code: str
    message: str


@dataclass
class ContractFailure:
    """A single contract constraint violation.

    Attributes:
        symbol_id: Fully-qualified symbol identifier, e.g.
            ``"local_sage/model/client.py::OllamaClient.generate"``.
        constraint: The contract constraint that was violated, e.g.
            ``"exception_types"`` or ``"return_shape"``.
        actual: Description of what was actually found in the code.
    """

    symbol_id: str
    constraint: str
    actual: str


@dataclass
class ValidationFailure:
    """A single high-level validation failure from any tool.

    Attributes:
        tool: Name of the tool that produced the failure.
            One of ``"pytest"``, ``"mypy"``, ``"ruff"``, ``"contracts"``.
        message: Human-readable description of the failure.
    """

    tool: str
    message: str


@dataclass
class ValidationResult:
    """Aggregate result of a full validation run across all four validators.

    Attributes:
        passed: ``True`` if all validators passed, ``False`` otherwise.
        failures: High-level list of failures from all tools.
        pytest_counts: Pass/fail/error counts from pytest, or ``None`` if
            pytest was not run.
        mypy_errors: List of mypy errors, or ``None`` if mypy was not run.
        ruff_violations: List of ruff violations, or ``None`` if ruff was
            not run.
        contract_failures: List of contract failures, or ``None`` if the
            contract checker was not run.
        duration_ms: Total wall-clock time for the validation run in
            milliseconds.
    """

    passed: bool
    failures: list[ValidationFailure]
    pytest_counts: PytestCounts | None
    mypy_errors: list[MypyError] | None
    ruff_violations: list[RuffViolation] | None
    contract_failures: list[ContractFailure] | None
    duration_ms: int

    def to_retry_prompt(self) -> str:
        """Format failures as a prompt suffix for the code generator.

        Produces a human-readable block describing every validation failure
        so the code generator can use it as context when retrying.

        Returns:
            A formatted string listing all failures grouped by tool, or an
            empty string if there are no failures.
        """
        if not self.failures:
            return ""

        sections: list[str] = ["Validation failed. Please fix the following issues:\n"]
        sections += self._pytest_section()
        sections += self._mypy_section()
        sections += self._ruff_section()
        sections += self._contracts_section()
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Private helpers — each ≤ 15 lines so the parent stays under 40
    # ------------------------------------------------------------------

    def _pytest_section(self) -> list[str]:
        """Build the PYTEST section lines, if any pytest failures exist."""
        pytest_failures = [f for f in self.failures if f.tool == "pytest"]
        if not pytest_failures:
            return []
        lines = [f"\nPYTEST ({len(pytest_failures)} failure(s)):"]
        for failure in pytest_failures:
            lines.append(f"  - {failure.message}")
        return lines

    def _mypy_section(self) -> list[str]:
        """Build the MYPY section lines, if any mypy errors exist."""
        if not self.mypy_errors:
            return []
        lines = [f"\nMYPY ({len(self.mypy_errors)} error(s)):"]
        for err in self.mypy_errors:
            lines.append(
                f"  - {err.file_path}:{err.line}:{err.column}:"
                f" error: {err.message} [{err.error_code}]"
            )
        return lines

    def _ruff_section(self) -> list[str]:
        """Build the RUFF section lines, if any ruff violations exist."""
        if not self.ruff_violations:
            return []
        lines = [f"\nRUFF ({len(self.ruff_violations)} violation(s)):"]
        for v in self.ruff_violations:
            lines.append(f"  - {v.file_path}:{v.line}:{v.column}: {v.rule_code} {v.message}")
        return lines

    def _contracts_section(self) -> list[str]:
        """Build the CONTRACTS section lines, if any contract failures exist."""
        if not self.contract_failures:
            return []
        lines = [f"\nCONTRACTS ({len(self.contract_failures)} failure(s)):"]
        for cf in self.contract_failures:
            lines.append(f"  - {cf.symbol_id}: {cf.constraint}: {cf.actual}")
        return lines
