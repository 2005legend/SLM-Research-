"""Unit and property-based tests for ValidationRunner (Layer 6 — Validation).

Covers validate_and_apply(), validate_only(), _run_all_checks(), and
_prompt_manual_review(), plus:

- Property 19: All four validators are called before patch application
- Property 21: ValidationTimeoutError identifies the timed-out tool
- Property 23: Manual review gate prevents patch application without confirmation

**Validates: Requirements 6.1, 6.2, 6.3, 6.7, 6.11**
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.validation.exceptions import ValidationTimeoutError
from local_sage.validation.result import (
    MypyError,
    PytestCounts,
    ValidationFailure,
    ValidationResult,
)
from local_sage.validation.runner import ValidationRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passing_pytest_counts() -> PytestCounts:
    """Return a PytestCounts with no failures or errors."""
    return PytestCounts(passed=5, failed=0, errors=0)


def _failing_pytest_counts() -> PytestCounts:
    """Return a PytestCounts with one failure."""
    return PytestCounts(passed=4, failed=1, errors=0)


def _passing_result() -> ValidationResult:
    """Return a ValidationResult with passed=True and no failures."""
    return ValidationResult(
        passed=True,
        failures=[],
        pytest_counts=_passing_pytest_counts(),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=100,
    )


def _failing_result() -> ValidationResult:
    """Return a ValidationResult with passed=False and one pytest failure."""
    return ValidationResult(
        passed=False,
        failures=[ValidationFailure(tool="pytest", message="1 failed, 0 errors")],
        pytest_counts=_failing_pytest_counts(),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=100,
    )


def _make_runner(tmp_path: Path, manual_review: bool = False) -> ValidationRunner:
    """Create a ValidationRunner pointed at tmp_path.

    Args:
        tmp_path: Repository root path.
        manual_review: Whether to enable manual review mode.

    Returns:
        A configured ValidationRunner instance.
    """
    return ValidationRunner(
        repo_root=tmp_path,
        manual_review=manual_review,
        pytest_timeout=60,
        mypy_timeout=60,
        ruff_timeout=30,
    )


def _valid_patch(tmp_path: Path) -> str:
    """Create a target file and return a minimal valid unified diff."""
    (tmp_path / "foo.py").write_text("old\n", encoding="utf-8")
    return "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"


# ---------------------------------------------------------------------------
# Unit tests — validate_only()
# ---------------------------------------------------------------------------


class TestValidateOnly:
    """Unit tests for ValidationRunner.validate_only()."""

    def test_validate_only_never_calls_apply_to_repo_on_pass(self, tmp_path: Path) -> None:
        """validate_only() never calls apply_to_repo even when all checks pass."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo") as mock_apply,
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            result = runner.validate_only(_valid_patch(tmp_path))

        mock_apply.assert_not_called()
        assert result.passed is True

    def test_validate_only_never_calls_apply_to_repo_on_failure(self, tmp_path: Path) -> None:
        """validate_only() never calls apply_to_repo when checks fail."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo") as mock_apply,
            patch.object(runner._pytest_runner, "run", return_value=_failing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            result = runner.validate_only(_valid_patch(tmp_path))

        mock_apply.assert_not_called()
        assert result.passed is False

    def test_validate_only_cleans_up_temp_dir(self, tmp_path: Path) -> None:
        """validate_only() calls revert() in the finally block."""
        runner = _make_runner(tmp_path)
        fake_temp = tmp_path / "fake_temp"

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=fake_temp),
            patch.object(runner._patcher, "revert") as mock_revert,
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            runner.validate_only(_valid_patch(tmp_path))

        mock_revert.assert_called_once_with(fake_temp)

    def test_validate_only_cleans_up_even_on_timeout(self, tmp_path: Path) -> None:
        """validate_only() calls revert() even when a timeout error is raised."""
        runner = _make_runner(tmp_path)
        fake_temp = tmp_path / "fake_temp"

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=fake_temp),
            patch.object(runner._patcher, "revert") as mock_revert,
            patch.object(
                runner._pytest_runner,
                "run",
                side_effect=ValidationTimeoutError(
                    "pytest timed out", tool="pytest", timeout_seconds=60
                ),
            ),
            pytest.raises(ValidationTimeoutError),
        ):
            runner.validate_only(_valid_patch(tmp_path))

        mock_revert.assert_called_once_with(fake_temp)


# ---------------------------------------------------------------------------
# Unit tests — validate_and_apply()
# ---------------------------------------------------------------------------


class TestValidateAndApply:
    """Unit tests for ValidationRunner.validate_and_apply()."""

    def test_validate_and_apply_calls_apply_to_repo_when_all_pass(self, tmp_path: Path) -> None:
        """validate_and_apply() calls apply_to_repo when all validators pass."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo") as mock_apply,
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            result = runner.validate_and_apply(_valid_patch(tmp_path))

        mock_apply.assert_called_once()
        assert result.passed is True

    def test_validate_and_apply_does_not_call_apply_to_repo_on_failure(
        self, tmp_path: Path
    ) -> None:
        """validate_and_apply() does not call apply_to_repo when checks fail."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo") as mock_apply,
            patch.object(runner._pytest_runner, "run", return_value=_failing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            result = runner.validate_and_apply(_valid_patch(tmp_path))

        mock_apply.assert_not_called()
        assert result.passed is False

    def test_validate_and_apply_cleans_up_temp_dir(self, tmp_path: Path) -> None:
        """validate_and_apply() calls revert() in the finally block."""
        runner = _make_runner(tmp_path)
        fake_temp = tmp_path / "fake_temp"

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=fake_temp),
            patch.object(runner._patcher, "revert") as mock_revert,
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
            patch.object(runner._patcher, "apply_to_repo"),
        ):
            runner.validate_and_apply(_valid_patch(tmp_path))

        mock_revert.assert_called_once_with(fake_temp)


# ---------------------------------------------------------------------------
# Unit tests — _run_all_checks() validator call order
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    """Unit tests for ValidationRunner._run_all_checks() validator sequencing."""

    def test_all_four_validators_are_called(self, tmp_path: Path) -> None:
        """_run_all_checks() calls all four validators."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(
                runner._pytest_runner, "run", return_value=_passing_pytest_counts()
            ) as mock_pytest,
            patch.object(runner._mypy_runner, "run", return_value=[]) as mock_mypy,
            patch.object(runner._ruff_runner, "run", return_value=[]) as mock_ruff,
            patch.object(runner._contract_checker, "check", return_value=[]) as mock_contracts,
        ):
            runner._run_all_checks(tmp_path)

        mock_pytest.assert_called_once()
        mock_mypy.assert_called_once()
        mock_ruff.assert_called_once()
        mock_contracts.assert_called_once()

    def test_mypy_and_ruff_still_called_when_pytest_fails(self, tmp_path: Path) -> None:
        """_run_all_checks() calls mypy and ruff even when pytest reports failures."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._pytest_runner, "run", return_value=_failing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]) as mock_mypy,
            patch.object(runner._ruff_runner, "run", return_value=[]) as mock_ruff,
            patch.object(runner._contract_checker, "check", return_value=[]) as mock_contracts,
        ):
            runner._run_all_checks(tmp_path)

        mock_mypy.assert_called_once()
        mock_ruff.assert_called_once()
        mock_contracts.assert_called_once()

    def test_timeout_from_pytest_skips_remaining_validators(self, tmp_path: Path) -> None:
        """_run_all_checks() skips mypy/ruff/contracts when pytest times out."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(
                runner._pytest_runner,
                "run",
                side_effect=ValidationTimeoutError(
                    "pytest timed out", tool="pytest", timeout_seconds=60
                ),
            ),
            patch.object(runner._mypy_runner, "run", return_value=[]) as mock_mypy,
            patch.object(runner._ruff_runner, "run", return_value=[]) as mock_ruff,
            patch.object(runner._contract_checker, "check", return_value=[]) as mock_contracts,
        ):
            with pytest.raises(ValidationTimeoutError):
                runner._run_all_checks(tmp_path)

        mock_mypy.assert_not_called()
        mock_ruff.assert_not_called()
        mock_contracts.assert_not_called()

    def test_result_passed_is_true_when_all_validators_pass(self, tmp_path: Path) -> None:
        """_run_all_checks() returns ValidationResult(passed=True) when all pass."""
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            result = runner._run_all_checks(tmp_path)

        assert result.passed is True
        assert result.failures == []

    def test_result_passed_is_false_when_any_validator_fails(self, tmp_path: Path) -> None:
        """_run_all_checks() returns ValidationResult(passed=False) when any validator fails."""
        runner = _make_runner(tmp_path)
        mypy_error = MypyError(
            file_path=Path("a.py"), line=1, column=1, error_code="misc", message="type error"
        )

        with (
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[mypy_error]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            result = runner._run_all_checks(tmp_path)

        assert result.passed is False
        assert any(f.tool == "mypy" for f in result.failures)


# ---------------------------------------------------------------------------
# Unit tests — _prompt_manual_review()
# ---------------------------------------------------------------------------


class TestPromptManualReview:
    """Unit tests for ValidationRunner._prompt_manual_review()."""

    def test_returns_true_when_user_enters_y(self, tmp_path: Path) -> None:
        """_prompt_manual_review() returns True when user inputs 'y'."""
        runner = _make_runner(tmp_path)
        result = _passing_result()

        with patch("builtins.input", return_value="y"):
            confirmed = runner._prompt_manual_review(result)

        assert confirmed is True

    def test_returns_false_when_user_enters_n(self, tmp_path: Path) -> None:
        """_prompt_manual_review() returns False when user inputs 'n'."""
        runner = _make_runner(tmp_path)
        result = _passing_result()

        with patch("builtins.input", return_value="n"):
            confirmed = runner._prompt_manual_review(result)

        assert confirmed is False

    def test_returns_false_when_user_enters_empty_string(self, tmp_path: Path) -> None:
        """_prompt_manual_review() returns False when user inputs empty string."""
        runner = _make_runner(tmp_path)
        result = _passing_result()

        with patch("builtins.input", return_value=""):
            confirmed = runner._prompt_manual_review(result)

        assert confirmed is False

    def test_returns_false_when_user_enters_yes(self, tmp_path: Path) -> None:
        """_prompt_manual_review() returns False for 'yes' (only 'y' is accepted)."""
        runner = _make_runner(tmp_path)
        result = _passing_result()

        with patch("builtins.input", return_value="yes"):
            confirmed = runner._prompt_manual_review(result)

        assert confirmed is False


# ---------------------------------------------------------------------------
# Property 19: All four validators are called before patch application
# ---------------------------------------------------------------------------


@given(patch_text=st.text(min_size=0, max_size=50))
@settings(max_examples=100)
def test_property_19_all_validators_called_before_apply(
    patch_text: str,
) -> None:
    """Property 19: All four validators are called before patch application.

    For any patch string, ValidationRunner.validate_and_apply() SHALL invoke
    PytestRunner.run(), MypyRunner.run(), RuffRunner.run(), and
    ContractChecker.check() before calling Patcher.apply_to_repo(). If any
    of the four raises or returns failures, apply_to_repo SHALL NOT be called.

    # Feature: local-sage, Property 19: All four validators are called before patch application
    **Validates: Requirements 6.1, 6.2, 6.3**
    """
    # Feature: local-sage, Property 19: All four validators are called before patch application
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runner = _make_runner(tmp_path)
        call_order: list[str] = []

        def record(name: str):  # type: ignore[return]
            """Return a side-effect function that records the call name."""

            def _side_effect(*args, **kwargs):  # type: ignore[return]
                call_order.append(name)
                if name == "pytest":
                    return _passing_pytest_counts()
                if name in ("mypy", "ruff"):
                    return []
                if name == "contracts":
                    return []

            return _side_effect

        def record_apply(*args, **kwargs) -> None:  # type: ignore[return]
            call_order.append("apply_to_repo")

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo", side_effect=record_apply),
            patch.object(runner._pytest_runner, "run", side_effect=record("pytest")),
            patch.object(runner._mypy_runner, "run", side_effect=record("mypy")),
            patch.object(runner._ruff_runner, "run", side_effect=record("ruff")),
            patch.object(runner._contract_checker, "check", side_effect=record("contracts")),
            patch.object(ValidationRunner, "_pre_validate", return_value=None),
        ):
            runner.validate_and_apply(patch_text)

        # All four validators must appear before apply_to_repo
        assert "pytest" in call_order
        assert "mypy" in call_order
        assert "ruff" in call_order
        assert "contracts" in call_order
        assert "apply_to_repo" in call_order

        apply_idx = call_order.index("apply_to_repo")
        for validator in ("pytest", "mypy", "ruff", "contracts"):
            assert call_order.index(validator) < apply_idx


@given(patch_text=st.text(min_size=0, max_size=50))
@settings(max_examples=100)
def test_property_19_apply_not_called_when_validator_fails(
    patch_text: str,
) -> None:
    """Property 19 (failure branch): apply_to_repo is NOT called when any validator fails.

    # Feature: local-sage, Property 19: All four validators are called before patch application
    **Validates: Requirements 6.1, 6.2, 6.3**
    """
    # Feature: local-sage, Property 19: All four validators are called before patch application
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runner = _make_runner(tmp_path)

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo") as mock_apply,
            # pytest returns a failure
            patch.object(runner._pytest_runner, "run", return_value=_failing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
            patch.object(ValidationRunner, "_pre_validate", return_value=None),
        ):
            result = runner.validate_and_apply(patch_text)

        mock_apply.assert_not_called()
        assert result.passed is False


# ---------------------------------------------------------------------------
# Property 21: ValidationTimeoutError identifies the timed-out tool
# ---------------------------------------------------------------------------


@given(
    tool_name=st.sampled_from(["pytest", "mypy", "ruff"]),
    timeout_seconds=st.integers(min_value=1, max_value=300),
)
@settings(max_examples=100)
def test_property_21_timeout_error_identifies_tool(
    tool_name: str,
    timeout_seconds: int,
) -> None:
    """Property 21: ValidationTimeoutError identifies the timed-out tool.

    For any of the three subprocess tools (pytest, mypy, ruff), when that
    tool's subprocess exceeds its configured timeout, ValidationRunner SHALL
    raise a ValidationTimeoutError whose tool attribute equals the name of
    the timed-out tool.

    # Feature: local-sage, Property 21: ValidationTimeoutError identifies the timed-out tool
    **Validates: Requirements 6.7**
    """
    # Feature: local-sage, Property 21: ValidationTimeoutError identifies the timed-out tool
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runner = _make_runner(tmp_path)
        timeout_error = ValidationTimeoutError(
            f"{tool_name} timed out after {timeout_seconds} seconds",
            tool=tool_name,
            timeout_seconds=timeout_seconds,
        )

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(
                runner._pytest_runner,
                "run",
                side_effect=timeout_error if tool_name == "pytest" else None,
                return_value=None if tool_name == "pytest" else _passing_pytest_counts(),
            ),
            patch.object(
                runner._mypy_runner,
                "run",
                side_effect=timeout_error if tool_name == "mypy" else None,
                return_value=None if tool_name == "mypy" else [],
            ),
            patch.object(
                runner._ruff_runner,
                "run",
                side_effect=timeout_error if tool_name == "ruff" else None,
                return_value=None if tool_name == "ruff" else [],
            ),
            patch.object(runner._contract_checker, "check", return_value=[]),
        ):
            with pytest.raises(ValidationTimeoutError) as exc_info:
                runner.validate_only(_valid_patch(tmp_path))

        assert exc_info.value.tool == tool_name
        assert exc_info.value.timeout_seconds == timeout_seconds


# ---------------------------------------------------------------------------
# Property 23: Manual review gate prevents patch application without confirmation
# ---------------------------------------------------------------------------


@given(
    user_input=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=0,
        max_size=20,
    ).filter(lambda s: s.strip().lower() != "y"),
)
@settings(max_examples=100)
def test_property_23_manual_review_blocks_apply_without_y(
    user_input: str,
) -> None:
    """Property 23: Manual review gate prevents patch application without 'y'.

    When manual_review=True, ValidationRunner.validate_and_apply() SHALL NOT
    call Patcher.apply_to_repo() unless the user explicitly confirms with 'y'.
    Any other input → patch NOT applied.

    # Feature: local-sage, Property 23: Manual review gate prevents patch application without confirmation
    **Validates: Requirements 6.11**
    """
    # Feature: local-sage, Property 23: Manual review gate prevents patch application without confirmation
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runner = _make_runner(tmp_path, manual_review=True)

        with (
            patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
            patch.object(runner._patcher, "revert"),
            patch.object(runner._patcher, "apply_to_repo") as mock_apply,
            patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
            patch.object(runner._mypy_runner, "run", return_value=[]),
            patch.object(runner._ruff_runner, "run", return_value=[]),
            patch.object(runner._contract_checker, "check", return_value=[]),
            patch("builtins.input", return_value=user_input),
        ):
            result = runner.validate_and_apply(_valid_patch(tmp_path))

        mock_apply.assert_not_called()
        assert result.passed is True


def test_property_23_manual_review_applies_patch_on_y_confirmation(
    tmp_path: Path,
) -> None:
    """Property 23 (confirmation branch): apply_to_repo IS called when user enters 'y'.

    # Feature: local-sage, Property 23: Manual review gate prevents patch application without confirmation
    **Validates: Requirements 6.11**
    """
    # Feature: local-sage, Property 23: Manual review gate prevents patch application without confirmation
    runner = _make_runner(tmp_path, manual_review=True)

    with (
        patch.object(runner._patcher, "apply_to_temp", return_value=tmp_path),
        patch.object(runner._patcher, "revert"),
        patch.object(runner._patcher, "apply_to_repo") as mock_apply,
        patch.object(runner._pytest_runner, "run", return_value=_passing_pytest_counts()),
        patch.object(runner._mypy_runner, "run", return_value=[]),
        patch.object(runner._ruff_runner, "run", return_value=[]),
        patch.object(runner._contract_checker, "check", return_value=[]),
        patch("builtins.input", return_value="y"),
    ):
        result = runner.validate_and_apply(_valid_patch(tmp_path))

    mock_apply.assert_called_once()
    assert result.passed is True
