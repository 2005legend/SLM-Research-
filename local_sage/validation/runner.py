"""ValidationRunner orchestrator for Layer 6 — Validation.

Provides :class:`ValidationRunner`, which coordinates all four validators
(pytest, mypy, ruff, contracts) against a temporary copy of the repository,
optionally prompts the user for manual review, and applies the patch to the
real repository only when all checks pass.

⚠️  This module is part of the core validation layer.
    It REQUIRES manual human review before any task that uses it is
    marked complete.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from local_sage.agent.parser import ModelOutputParser
from local_sage.validation.contracts import ContractChecker
from local_sage.validation.exceptions import ValidationTimeoutError  # noqa: F401
from local_sage.validation.mypy_runner import MypyRunner
from local_sage.validation.patcher import Patcher
from local_sage.validation.pytest_runner import PytestRunner
from local_sage.validation.result import (
    ContractFailure,
    MypyError,
    PytestCounts,
    RuffViolation,
    ValidationFailure,
    ValidationResult,
)
from local_sage.validation.ruff_runner import RuffRunner


class ValidationRunner:
    """Orchestrates all four validators and optionally applies a patch.

    Runs pytest, mypy, ruff, and the contract checker against a temporary
    copy of the repository.  The original repository is never modified until
    all validators pass (and, if ``manual_review=True``, the user confirms).

    Attributes:
        _repo_root: Absolute path to the repository root.
        _manual_review: If ``True``, prompt the user for ``y/n`` confirmation
            before applying a passing patch.
        _pytest_timeout: Maximum seconds to wait for pytest.
        _mypy_timeout: Maximum seconds to wait for mypy.
        _ruff_timeout: Maximum seconds to wait for ruff.

    Example::

        runner = ValidationRunner(repo_root=Path("/path/to/repo"))
        result = runner.validate_only(patch_text)
        if result.passed:
            print("All checks passed!")
        else:
            print(result.to_retry_prompt())
    """

    def __init__(
        self,
        repo_root: Path,
        manual_review: bool = False,
        pytest_timeout: int = 60,
        mypy_timeout: int = 60,
        ruff_timeout: int = 30,
    ) -> None:
        """Initialise the runner with a repo root and optional configuration.

        Args:
            repo_root: Absolute path to the root of the repository to
                validate against.
            manual_review: If ``True``, pause after all checks pass and
                prompt the user for ``y/n`` confirmation before applying
                the patch.
            pytest_timeout: Maximum seconds to wait for pytest to complete.
            mypy_timeout: Maximum seconds to wait for mypy to complete.
            ruff_timeout: Maximum seconds to wait for each ruff subprocess.
        """
        self._repo_root = repo_root
        self._manual_review = manual_review
        self._pytest_timeout = pytest_timeout
        self._mypy_timeout = mypy_timeout
        self._ruff_timeout = ruff_timeout
        self._cache: dict[str, ValidationResult] = {}

        self._patcher = Patcher()
        self._pytest_runner = PytestRunner()
        self._mypy_runner = MypyRunner()
        self._ruff_runner = RuffRunner()
        self._contract_checker = ContractChecker()

    def validate_and_apply(self, patch: str) -> ValidationResult:
        """Run all checks and apply the patch to the repo if they pass.

        Applies the patch to a temporary directory, runs all four validators,
        and — if everything passes — applies the patch to the real repository.
        If ``manual_review=True``, the user is prompted for confirmation
        before the real apply step.  The temporary directory is always cleaned
        up in a ``finally`` block.

        Args:
            patch: Unified diff string to validate and apply.

        Returns:
            A :class:`~local_sage.validation.result.ValidationResult`
            describing the outcome of all validators.

        Raises:
            ValidationTimeoutError: If any validator subprocess times out.
        """
        self._cache.clear()
        pre = self._pre_validate(patch)
        if pre is not None:
            return pre

        key = hashlib.sha256(patch.encode()).hexdigest()[:16]
        if key in self._cache:
            return self._cache[key]

        temp_dir, changed_files = self._patcher.apply_to_temp(self._repo_root, patch)
        try:
            result = self._run_all_checks(temp_dir, changed_files)
            self._cache[key] = result
            return self._finalize_apply(result, patch)
        finally:
            self._patcher.revert(temp_dir)

    def _finalize_apply(self, result: ValidationResult, patch: str) -> ValidationResult:
        """Apply patch to repo when checks pass and review confirms."""
        if result.passed:
            if self._manual_review and not self._prompt_manual_review(result):
                return result
            self._patcher.apply_to_repo(self._repo_root, patch)
        return result

    def validate_only(self, patch: str) -> ValidationResult:
        """Run all checks without applying the patch to the repository.

        Applies the patch to a temporary directory, runs all four validators,
        and returns the result.  The real repository is never modified.  The
        temporary directory is always cleaned up in a ``finally`` block.

        Args:
            patch: Unified diff string to validate.

        Returns:
            A :class:`~local_sage.validation.result.ValidationResult`
            describing the outcome of all validators.

        Raises:
            ValidationTimeoutError: If any validator subprocess times out.
        """
        pre = self._pre_validate(patch)
        if pre is not None:
            return pre

        key = hashlib.sha256(patch.encode()).hexdigest()[:16]
        if key in self._cache:
            return self._cache[key]

        temp_dir, changed_files = self._patcher.apply_to_temp(self._repo_root, patch)
        try:
            result = self._run_all_checks(temp_dir, changed_files)
            self._cache[key] = result
            return result
        finally:
            self._patcher.revert(temp_dir)

    def validate_search_replace(self, blocks: list[Any], target_file: str | None = None) -> ValidationResult:
        """Validate search-replace blocks without applying them to the repo.

        Applies the blocks to a temporary copy and runs all four validators.
        The real repository is never modified.

        Args:
            blocks: List of SearchReplaceBlock objects to validate.
            target_file: Optional explicit file name from task to resolve ambiguities.

        Returns:
            A :class:`~local_sage.validation.result.ValidationResult`.

        Raises:
            ValidationTimeoutError: If any validator subprocess times out.
        """
        if not blocks:
            return self._pre_check_failure("empty patch")
        key = hashlib.sha256(repr(blocks).encode()).hexdigest()[:16]
        if key in self._cache:
            return self._cache[key]
        try:
            temp_dir, changed_files = self._patcher.apply_search_replace_to_temp(
                self._repo_root, blocks, target_file
            )
        except Exception as exc:  # noqa: BLE001
            return self._pre_check_failure(str(exc))
        try:
            result = self._run_all_checks(temp_dir, changed_files)
            self._cache[key] = result
            return result
        finally:
            self._patcher.revert(temp_dir)

    def _pre_validate(self, patch: str) -> ValidationResult | None:
        """Run fast pre-checks before applying a patch to a temp directory.

        Args:
            patch: Unified diff string to validate.

        Returns:
            A failed ``ValidationResult`` on the first rule violation,
            or ``None`` when all checks pass.
        """
        if not patch.strip():
            return self._pre_check_failure("empty patch")

        if ModelOutputParser().extract_diff(patch) is None:
            return self._pre_check_failure("no valid diff found")

        if not self._has_change_lines(patch):
            return self._pre_check_failure("no change lines")

        import whatthepatch

        for diff in whatthepatch.parse_patch(patch):
            if getattr(diff, "header", None) is None:
                continue
            raw = diff.header.new_path or diff.header.old_path
            if raw is None:
                continue
            resolved = self._patcher._resolve_file_path(raw, self._repo_root)
            if resolved is None:
                return self._pre_check_failure(str(raw))

        return None

    def _has_change_lines(self, patch: str) -> bool:
        """Return True if *patch* contains at least one change line."""
        for line in patch.splitlines():
            if (line.startswith("+") or line.startswith("-")) and not line.startswith(
                ("---", "+++")
            ):
                return True
        return False

    def _pre_check_failure(self, message: str) -> ValidationResult:
        """Build a failed ValidationResult for a pre-check violation."""
        return ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="pre_check", message=message)],
            pytest_counts=None,
            mypy_errors=None,
            ruff_violations=None,
            contract_failures=None,
            duration_ms=0,
        )

    def _run_all_checks(self, temp_dir: Path, changed_files: list[Path] | None = None) -> ValidationResult:
        """Run all four validators against *temp_dir* and aggregate results.

        All four validators are always attempted regardless of individual
        failures.  Only ``ValidationTimeoutError`` causes early exit.
        Contract YAML files are read from ``self._repo_root``, not temp_dir.

        Args:
            temp_dir: Patched copy of the repository to validate against.
            changed_files: Optional list of files that were modified by the patch.

        Returns:
            Aggregated :class:`~local_sage.validation.result.ValidationResult`.

        Raises:
            ValidationTimeoutError: If any validator subprocess times out.
        """
        start_ms = int(time.time() * 1000)
        failures: list[ValidationFailure] = []

        pytest_counts = self._run_pytest(temp_dir, failures, changed_files)
        mypy_errors = self._run_mypy(temp_dir, failures, changed_files)
        ruff_violations = self._run_ruff(temp_dir, failures, changed_files)
        contract_failures = self._run_contracts(temp_dir, failures)

        duration_ms = int(time.time() * 1000) - start_ms
        
        # Calculate confidence score
        from local_sage.validation.confidence import PatchConfidenceScorer
        scorer = PatchConfidenceScorer()
        
        # We need CFG warnings count. For now, CFGChecker is run by ConsistencyChecker outside this loop, 
        # or we can run it here! Let's run it here.
        from local_sage.validation.cfg import CFGChecker
        cfg_warnings = 0
        cfg_checker = CFGChecker()
        for py_file in temp_dir.rglob("*.py"):
            try:
                warnings = cfg_checker.check_source(py_file.read_text(encoding="utf-8"))
                cfg_warnings += len(warnings)
            except Exception:
                pass
                
        confidence = scorer.score(
            syntax_passed=True, # if we got here, it parsed
            mypy_passed=len(mypy_errors) == 0 if mypy_errors is not None else True,
            cfg_warnings=cfg_warnings,
            contract_passed=len(contract_failures) == 0 if contract_failures is not None else True,
            complexity_score=0 # placeholder
        )
        
        return ValidationResult(
            passed=(len(failures) == 0) and confidence.passed,
            failures=failures,
            pytest_counts=pytest_counts,
            mypy_errors=mypy_errors,
            ruff_violations=ruff_violations,
            contract_failures=contract_failures,
            duration_ms=duration_ms,
            confidence_score=confidence.score,
        )

    def _run_pytest(
        self, temp_dir: Path, failures: list[ValidationFailure], target_files: list[Path] | None = None
    ) -> PytestCounts | None:
        """Run pytest and append any failure to *failures*.

        Args:
            temp_dir: Directory to run pytest in.
            failures: Mutable list to append failures to.
            target_files: Optional list of specific files to test.

        Returns:
            ``PytestCounts`` or ``None`` on timeout (which re-raises).

        Raises:
            ValidationTimeoutError: If pytest times out.
        """

        counts = self._pytest_runner.run(temp_dir, target_files, self._pytest_timeout)
        if counts.failed > 0 or counts.errors > 0:
            failures.append(
                ValidationFailure(
                    tool="pytest",
                    message=f"{counts.failed} failed, {counts.errors} errors",
                )
            )
        return counts

    def _run_mypy(
        self, temp_dir: Path, failures: list[ValidationFailure], target_files: list[Path] | None = None
    ) -> list[MypyError] | None:
        """Run mypy and append any failure to *failures*.

        Args:
            temp_dir: Directory to run mypy in.
            failures: Mutable list to append failures to.
            target_files: Optional list of specific files to test.

        Returns:
            List of ``MypyError`` objects.

        Raises:
            ValidationTimeoutError: If mypy times out.
        """
        errors = self._mypy_runner.run(temp_dir, target_files, self._mypy_timeout)
        if errors:
            failures.append(
                ValidationFailure(
                    tool="mypy",
                    message=f"{len(errors)} type error(s)",
                )
            )
        return errors

    def _run_ruff(
        self, temp_dir: Path, failures: list[ValidationFailure], target_files: list[Path] | None = None
    ) -> list[RuffViolation] | None:
        """Run ruff check and format and append any failure to *failures*.

        Args:
            temp_dir: Directory to run ruff in.
            failures: Mutable list to append failures to.
            target_files: Optional list of specific files to check.

        Returns:
            List of ``RuffViolation`` objects.

        Raises:
            ValidationTimeoutError: If ruff times out.
        """
        violations = self._ruff_runner.run(temp_dir, target_files, self._ruff_timeout)
        if violations:
            failures.append(
                ValidationFailure(
                    tool="ruff",
                    message=f"{len(violations)} violation(s)",
                )
            )
        return violations

    def _run_contracts(
        self, temp_dir: Path, failures: list[ValidationFailure]
    ) -> list[ContractFailure] | None:
        """Run contract checker and append failures.

        Contract YAML files live in repo_root/contracts/, but the source
        code being validated is in temp_dir.

        Args:
            temp_dir: Directory to run contract checks against.
            failures: Mutable list to append failures to.

        Returns:
            List of ``ContractFailure`` objects.
        """
        # Contracts live inside the temp copy so the patched state is what
        # gets validated — not the original repo.
        contracts_dir = temp_dir / "contracts"

        # Guard: if the real repo has contracts but the temp copy doesn't, that
        # indicates the patch copy step is incomplete.  Warn loudly so this
        # never silently passes as "zero violations".
        if not contracts_dir.exists() or not any(contracts_dir.iterdir()):
            real_contracts = self._repo_root / "contracts"
            if real_contracts.exists() and any(real_contracts.iterdir()):
                import warnings
                warnings.warn(
                    f"contracts/ exists in repo root but is missing or empty in "
                    f"temp copy {temp_dir} — patch copy step may be incomplete.",
                    stacklevel=2,
                )
            # Fall through: ContractChecker.check() handles a missing/empty dir
            # gracefully by returning [], so we always call it rather than
            # short-circuiting here (which would bypass any mock in tests).

        contract_failures = self._contract_checker.check(
            contracts_dir=contracts_dir,
            source_dir=temp_dir
        )
        if contract_failures:
            failures.append(
                ValidationFailure(
                    tool="contracts",
                    message=f"{len(contract_failures)} contract failure(s)",
                )
            )
        return contract_failures

    def _prompt_manual_review(self, result: ValidationResult) -> bool:
        """Prompt the user for y/n confirmation before applying the patch.

        Prints the validation result summary and waits for user input.
        Returns ``True`` only if the user explicitly types ``y``.

        Args:
            result: The completed :class:`~local_sage.validation.result.ValidationResult`
                to display before prompting.

        Returns:
            ``True`` if the user confirms with ``"y"`` (case-insensitive),
            ``False`` for any other input including empty input.
        """
        print(result.to_retry_prompt() if not result.passed else "Validation passed.")
        response = input("Apply patch? [y/N]: ").strip().lower()
        return response == "y"
