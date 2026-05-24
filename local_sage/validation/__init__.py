"""Layer 6 — Validation: deterministic patch validation gate.

⚠️  This layer is the core novel contribution of local-sage.
    No implementation task in this layer should be marked complete without
    a human reviewing the generated code.

Public API:
    ValidationRunner   — orchestrates all four validators and applies patches.
    ValidationResult   — typed result from a validation run.
    PytestCounts       — pass/fail/error counts from pytest.
    MypyError          — a single mypy type error.
    RuffViolation      — a single ruff lint or format violation.
    ContractFailure    — a single contract constraint violation.
    Patcher            — applies unified diff patches to the repository.
    ValidationError         — base exception for all validation errors.
    ValidationTimeoutError  — raised when a subprocess tool times out.
    ContractParseError      — raised when a contract YAML file is malformed.
"""

from local_sage.validation.contracts import Contract, ContractChecker
from local_sage.validation.exceptions import (
    ContractParseError,
    ValidationError,
    ValidationTimeoutError,
)
from local_sage.validation.patcher import Patcher
from local_sage.validation.result import (
    ContractFailure,
    MypyError,
    PytestCounts,
    RuffViolation,
    ValidationFailure,
    ValidationResult,
)
from local_sage.validation.runner import ValidationRunner

__all__ = [
    "Contract",
    "ContractChecker",
    "ValidationRunner",
    "ValidationResult",
    "PytestCounts",
    "MypyError",
    "RuffViolation",
    "ContractFailure",
    "ValidationFailure",
    "Patcher",
    "ValidationError",
    "ValidationTimeoutError",
    "ContractParseError",
]
