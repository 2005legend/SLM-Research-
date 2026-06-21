"""Unit tests for ValidationResult and related dataclasses (Layer 6 — Validation).

Covers PytestCounts, MypyError, RuffViolation, ContractFailure, ValidationFailure,
and ValidationResult.to_retry_prompt().

**Validates: Requirements 6.1, 6.2, 6.3**
"""

from __future__ import annotations

from pathlib import Path

from local_sage.validation.result import (
    ContractFailure,
    MypyError,
    PytestCounts,
    RuffViolation,
    ValidationFailure,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Unit tests — PytestCounts
# ---------------------------------------------------------------------------


class TestPytestCounts:
    """Unit tests for the PytestCounts dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """PytestCounts stores passed, failed, and errors correctly."""
        counts = PytestCounts(passed=10, failed=2, errors=1)
        assert counts.passed == 10
        assert counts.failed == 2
        assert counts.errors == 1

    def test_construction_with_zero_values(self) -> None:
        """PytestCounts accepts all-zero values."""
        counts = PytestCounts(passed=0, failed=0, errors=0)
        assert counts.passed == 0
        assert counts.failed == 0
        assert counts.errors == 0

    def test_equality(self) -> None:
        """Two PytestCounts with identical fields are equal."""
        a = PytestCounts(passed=5, failed=1, errors=0)
        b = PytestCounts(passed=5, failed=1, errors=0)
        assert a == b

    def test_inequality(self) -> None:
        """Two PytestCounts with different fields are not equal."""
        a = PytestCounts(passed=5, failed=1, errors=0)
        b = PytestCounts(passed=5, failed=2, errors=0)
        assert a != b


# ---------------------------------------------------------------------------
# Unit tests — MypyError
# ---------------------------------------------------------------------------


class TestMypyError:
    """Unit tests for the MypyError dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """MypyError stores all fields correctly."""
        err = MypyError(
            file_path=Path("local_sage/model/client.py"),
            line=42,
            column=8,
            error_code="return-value",
            message="Incompatible return value type",
        )
        assert err.file_path == Path("local_sage/model/client.py")
        assert err.line == 42
        assert err.column == 8
        assert err.error_code == "return-value"
        assert err.message == "Incompatible return value type"

    def test_file_path_is_path_object(self) -> None:
        """MypyError.file_path is a pathlib.Path instance."""
        err = MypyError(
            file_path=Path("foo.py"),
            line=1,
            column=1,
            error_code="misc",
            message="some error",
        )
        assert isinstance(err.file_path, Path)

    def test_equality(self) -> None:
        """Two MypyError instances with identical fields are equal."""
        a = MypyError(Path("a.py"), 1, 1, "misc", "msg")
        b = MypyError(Path("a.py"), 1, 1, "misc", "msg")
        assert a == b


# ---------------------------------------------------------------------------
# Unit tests — RuffViolation
# ---------------------------------------------------------------------------


class TestRuffViolation:
    """Unit tests for the RuffViolation dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """RuffViolation stores all fields correctly."""
        v = RuffViolation(
            file_path=Path("local_sage/cli.py"),
            line=10,
            column=5,
            rule_code="E501",
            message="Line too long",
        )
        assert v.file_path == Path("local_sage/cli.py")
        assert v.line == 10
        assert v.column == 5
        assert v.rule_code == "E501"
        assert v.message == "Line too long"

    def test_format_violation_has_format_rule_code(self) -> None:
        """A FORMAT violation uses rule_code='FORMAT'."""
        v = RuffViolation(
            file_path=Path("."),
            line=0,
            column=0,
            rule_code="FORMAT",
            message="One or more files are not formatted correctly",
        )
        assert v.rule_code == "FORMAT"

    def test_equality(self) -> None:
        """Two RuffViolation instances with identical fields are equal."""
        a = RuffViolation(Path("a.py"), 1, 1, "E501", "msg")
        b = RuffViolation(Path("a.py"), 1, 1, "E501", "msg")
        assert a == b


# ---------------------------------------------------------------------------
# Unit tests — ContractFailure
# ---------------------------------------------------------------------------


class TestContractFailure:
    """Unit tests for the ContractFailure dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """ContractFailure stores symbol_id, constraint, and actual correctly."""
        cf = ContractFailure(
            symbol_id="local_sage/model/client.py::OllamaClient.generate",
            constraint="exception_types",
            actual="raises 'ValueError' which is not in ['OllamaError']",
        )
        assert cf.symbol_id == "local_sage/model/client.py::OllamaClient.generate"
        assert cf.constraint == "exception_types"
        assert "ValueError" in cf.actual

    def test_equality(self) -> None:
        """Two ContractFailure instances with identical fields are equal."""
        a = ContractFailure("sym", "exception_types", "actual")
        b = ContractFailure("sym", "exception_types", "actual")
        assert a == b


# ---------------------------------------------------------------------------
# Unit tests — ValidationResult.to_retry_prompt()
# ---------------------------------------------------------------------------


class TestValidationResultToRetryPrompt:
    """Unit tests for ValidationResult.to_retry_prompt()."""

    def _passing_result(self) -> ValidationResult:
        """Return a ValidationResult with passed=True and no failures."""
        return ValidationResult(
            passed=True,
            failures=[],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[],
            contract_failures=[],
            duration_ms=100,
        )

    def test_to_retry_prompt_returns_empty_string_when_no_failures(self) -> None:
        """to_retry_prompt() returns '' when there are no failures."""
        result = self._passing_result()
        assert result.to_retry_prompt() == ""

    def test_to_retry_prompt_includes_pytest_section_on_pytest_failure(
        self,
    ) -> None:
        """to_retry_prompt() includes a PYTEST section when pytest fails."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="pytest", message="2 failed, 0 errors")],
            pytest_counts=PytestCounts(passed=3, failed=2, errors=0),
            mypy_errors=[],
            ruff_violations=[],
            contract_failures=[],
            duration_ms=200,
        )
        prompt = result.to_retry_prompt()
        assert "PYTEST" in prompt
        assert "2 failed" in prompt

    def test_to_retry_prompt_includes_mypy_section_on_mypy_errors(
        self,
    ) -> None:
        """to_retry_prompt() includes a MYPY section when mypy errors exist."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="mypy", message="1 type error(s)")],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[
                MypyError(
                    file_path=Path("local_sage/foo.py"),
                    line=10,
                    column=4,
                    error_code="return-value",
                    message="Incompatible return value",
                )
            ],
            ruff_violations=[],
            contract_failures=[],
            duration_ms=150,
        )
        prompt = result.to_retry_prompt()
        assert "MYPY" in prompt
        assert "return-value" in prompt

    def test_to_retry_prompt_includes_ruff_section_on_ruff_violations(
        self,
    ) -> None:
        """to_retry_prompt() includes a RUFF section when ruff violations exist."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="ruff", message="1 violation(s)")],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[
                RuffViolation(
                    file_path=Path("local_sage/bar.py"),
                    line=5,
                    column=1,
                    rule_code="E501",
                    message="Line too long",
                )
            ],
            contract_failures=[],
            duration_ms=80,
        )
        prompt = result.to_retry_prompt()
        assert "RUFF" in prompt
        assert "E501" in prompt

    def test_to_retry_prompt_includes_contracts_section_on_contract_failures(
        self,
    ) -> None:
        """to_retry_prompt() includes a CONTRACTS section when contract failures exist."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="contracts", message="1 contract failure(s)")],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[],
            contract_failures=[
                ContractFailure(
                    symbol_id="local_sage/model/client.py::OllamaClient.generate",
                    constraint="exception_types",
                    actual="raises 'ValueError'",
                )
            ],
            duration_ms=90,
        )
        prompt = result.to_retry_prompt()
        assert "CONTRACTS" in prompt
        assert "exception_types" in prompt

    def test_to_retry_prompt_includes_all_sections_when_all_fail(self) -> None:
        """to_retry_prompt() includes all four sections when all validators fail."""
        result = ValidationResult(
            passed=False,
            failures=[
                ValidationFailure(tool="pytest", message="1 failed, 0 errors"),
                ValidationFailure(tool="mypy", message="1 type error(s)"),
                ValidationFailure(tool="ruff", message="1 violation(s)"),
                ValidationFailure(tool="contracts", message="1 contract failure(s)"),
            ],
            pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
            mypy_errors=[MypyError(Path("a.py"), 1, 1, "misc", "type error")],
            ruff_violations=[RuffViolation(Path("b.py"), 2, 1, "E501", "line too long")],
            contract_failures=[ContractFailure("sym::func", "exception_types", "raises X")],
            duration_ms=500,
        )
        prompt = result.to_retry_prompt()
        assert "PYTEST" in prompt
        assert "MYPY" in prompt
        assert "RUFF" in prompt
        assert "CONTRACTS" in prompt

    def test_to_retry_prompt_starts_with_validation_failed(self) -> None:
        """to_retry_prompt() starts with 'Validation failed.' when there are failures."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="pytest", message="1 failed, 0 errors")],
            pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
            mypy_errors=[],
            ruff_violations=[],
            contract_failures=[],
            duration_ms=100,
        )
        prompt = result.to_retry_prompt()
        assert prompt.startswith("Validation failed.")

    def test_to_retry_prompt_none_mypy_errors_skips_mypy_section(self) -> None:
        """to_retry_prompt() skips MYPY section when mypy_errors is None."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="pytest", message="1 failed, 0 errors")],
            pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
            mypy_errors=None,
            ruff_violations=None,
            contract_failures=None,
            duration_ms=100,
        )
        prompt = result.to_retry_prompt()
        assert "MYPY" not in prompt
        assert "RUFF" not in prompt
        assert "CONTRACTS" not in prompt

    def test_to_retry_prompt_appends_diff_format_note_on_format_only_ruff(self) -> None:
        """FORMAT-only ruff failure appends unified diff format guidance."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="ruff", message="1 violation(s)")],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[
                RuffViolation(
                    file_path=Path("."),
                    line=0,
                    column=0,
                    rule_code="FORMAT",
                    message="not formatted",
                )
            ],
            contract_failures=[],
            duration_ms=80,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" in prompt
        assert "--- a/file" in prompt
        assert "+++ b/file" in prompt
        assert "@@ ... @@ hunks" in prompt

    def test_to_retry_prompt_no_diff_note_on_non_format_ruff(self) -> None:
        """Non-FORMAT ruff failure does not append the diff format note."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="ruff", message="1 violation(s)")],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[
                RuffViolation(
                    file_path=Path("local_sage/bar.py"),
                    line=5,
                    column=1,
                    rule_code="E501",
                    message="Line too long",
                )
            ],
            contract_failures=[],
            duration_ms=80,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt


    def test_to_retry_prompt_no_diff_note_on_mixed_ruff_violations(self) -> None:
        """Mixed ruff violations (FORMAT + non-FORMAT) do not append the diff note.

        Even one non-FORMAT rule code means the note must be suppressed.
        """
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="ruff", message="2 violation(s)")],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[
                RuffViolation(
                    file_path=Path("local_sage/bar.py"),
                    line=0,
                    column=0,
                    rule_code="FORMAT",
                    message="not formatted",
                ),
                RuffViolation(
                    file_path=Path("local_sage/bar.py"),
                    line=5,
                    column=1,
                    rule_code="E501",
                    message="Line too long",
                ),
            ],
            contract_failures=[],
            duration_ms=80,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt
        assert "--- a/file" not in prompt

    def test_to_retry_prompt_no_diff_note_on_pytest_failure(self) -> None:
        """A pytest failure does not append the diff format note."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="pytest", message="1 failed, 0 errors")],
            pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
            mypy_errors=[],
            ruff_violations=[],
            contract_failures=[],
            duration_ms=200,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt
        assert "--- a/file" not in prompt

    def test_to_retry_prompt_no_diff_note_on_multiple_failures(self) -> None:
        """Multiple failures (including ruff FORMAT) do not append the diff note.

        The note only fires when the ONLY failure is FORMAT-only ruff.
        """
        result = ValidationResult(
            passed=False,
            failures=[
                ValidationFailure(tool="ruff", message="1 violation(s)"),
                ValidationFailure(tool="pytest", message="1 failed, 0 errors"),
            ],
            pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
            mypy_errors=[],
            ruff_violations=[
                RuffViolation(
                    file_path=Path("."),
                    line=0,
                    column=0,
                    rule_code="FORMAT",
                    message="not formatted",
                )
            ],
            contract_failures=[],
            duration_ms=150,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt
        assert "--- a/file" not in prompt


# ---------------------------------------------------------------------------
# Unit tests — ValidationResult.to_retry_prompt() — retry prompt enhancement
# (Requirements 3.1, 3.2, 3.3)
# ---------------------------------------------------------------------------


class TestRetryPromptDiffFormatNote:
    """Unit tests for the diff-format note appended by to_retry_prompt().

    Validates: Requirements 3.1, 3.2, 3.3
    """

    def test_retry_prompt_format_only_ruff_appends_note(self) -> None:
        """FORMAT-only ruff failure appends note with all four required substrings.

        The note must contain 'unified diff', '--- a/file', '+++ b/file',
        and '@@ ... @@ hunks' so the model receives unambiguous diff guidance.
        """
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="ruff", message="1 violation(s)")],
            pytest_counts=None,
            mypy_errors=None,
            ruff_violations=[
                RuffViolation(
                    file_path=Path("."),
                    line=0,
                    column=0,
                    rule_code="FORMAT",
                    message="not formatted",
                )
            ],
            contract_failures=None,
            duration_ms=50,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" in prompt
        assert "--- a/file" in prompt
        assert "+++ b/file" in prompt
        assert "@@ ... @@ hunks" in prompt

    def test_retry_prompt_mixed_failure_no_note(self) -> None:
        """Pytest failure does not append the unified diff note (regression guard)."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="pytest", message="1 failed, 0 errors")],
            pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
            mypy_errors=None,
            ruff_violations=None,
            contract_failures=None,
            duration_ms=120,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt

    def test_retry_prompt_multiple_ruff_failures_no_note(self) -> None:
        """Two ruff ValidationFailures do not trigger the diff-format note.

        The note only fires when there is exactly one failure and it is ruff.
        """
        result = ValidationResult(
            passed=False,
            failures=[
                ValidationFailure(tool="ruff", message="violation 1"),
                ValidationFailure(tool="ruff", message="violation 2"),
            ],
            pytest_counts=None,
            mypy_errors=None,
            ruff_violations=[
                RuffViolation(
                    file_path=Path("a.py"),
                    line=1,
                    column=1,
                    rule_code="FORMAT",
                    message="not formatted",
                ),
                RuffViolation(
                    file_path=Path("b.py"),
                    line=2,
                    column=1,
                    rule_code="FORMAT",
                    message="not formatted",
                ),
            ],
            contract_failures=None,
            duration_ms=60,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt

    def test_retry_prompt_ruff_non_format_no_note(self) -> None:
        """Ruff failure with a non-FORMAT rule_code does not append the note."""
        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="ruff", message="1 violation(s)")],
            pytest_counts=None,
            mypy_errors=None,
            ruff_violations=[
                RuffViolation(
                    file_path=Path("local_sage/foo.py"),
                    line=10,
                    column=1,
                    rule_code="E501",
                    message="Line too long",
                )
            ],
            contract_failures=None,
            duration_ms=40,
        )
        prompt = result.to_retry_prompt()
        assert "unified diff" not in prompt

    def test_retry_prompt_empty_no_failures(self) -> None:
        """ValidationResult with passed=True and no failures returns empty string."""
        result = ValidationResult(
            passed=True,
            failures=[],
            pytest_counts=None,
            mypy_errors=None,
            ruff_violations=None,
            contract_failures=None,
            duration_ms=10,
        )
        assert result.to_retry_prompt() == ""
