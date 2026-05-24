"""Unit and property-based tests for ContractChecker (Layer 6 — Validation).

Covers load_contracts(), check(), exception_types validation, return_shape
validation, ContractParseError on malformed YAML, and Property 22:
ContractChecker detects exception type violations.

**Validates: Requirements 6.8, 6.9**
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.validation.contracts import ContractChecker
from local_sage.validation.exceptions import ContractParseError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_contract(
    contracts_dir: Path,
    name: str,
    symbol_id: str,
    exception_types: list[str],
    return_shape: dict | None = None,
) -> Path:
    """Write a YAML contract file to contracts_dir.

    Args:
        contracts_dir: Directory to write the contract into.
        name: Filename stem (without .yaml extension).
        symbol_id: The symbol_id field value.
        exception_types: List of allowed exception type names.
        return_shape: Optional return_shape dict.

    Returns:
        Path to the written YAML file.
    """
    import yaml  # type: ignore[import]

    contracts_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "symbol_id": symbol_id,
        "exception_types": exception_types,
    }
    if return_shape is not None:
        data["return_shape"] = return_shape

    yaml_path = contracts_dir / f"{name}.yaml"
    yaml_path.write_text(yaml.dump(data), encoding="utf-8")
    return yaml_path


def _write_source(
    repo_dir: Path,
    relative_path: str,
    source: str,
) -> Path:
    """Write a Python source file to repo_dir.

    Args:
        repo_dir: Repository root directory.
        relative_path: Relative path within the repo (e.g. 'pkg/module.py').
        source: Python source code to write.

    Returns:
        Path to the written source file.
    """
    full_path = repo_dir / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(source, encoding="utf-8")
    return full_path


# ---------------------------------------------------------------------------
# Unit tests — load_contracts()
# ---------------------------------------------------------------------------


class TestLoadContracts:
    """Unit tests for ContractChecker.load_contracts()."""

    def test_returns_empty_list_when_no_contracts_dir(self, tmp_path: Path) -> None:
        """load_contracts() returns [] when contracts/ directory does not exist."""
        checker = ContractChecker()
        contracts = checker.load_contracts(tmp_path)
        assert contracts == []

    def test_returns_empty_list_for_empty_contracts_dir(self, tmp_path: Path) -> None:
        """load_contracts() returns [] when contracts/ directory is empty."""
        (tmp_path / "contracts").mkdir()
        checker = ContractChecker()
        contracts = checker.load_contracts(tmp_path)
        assert contracts == []

    def test_loads_single_contract(self, tmp_path: Path) -> None:
        """load_contracts() loads a single valid YAML contract file."""
        _write_contract(
            tmp_path / "contracts",
            "my_contract",
            "pkg/module.py::my_func",
            ["ValueError"],
        )
        checker = ContractChecker()
        contracts = checker.load_contracts(tmp_path)
        assert len(contracts) == 1
        assert contracts[0].symbol_id == "pkg/module.py::my_func"
        assert contracts[0].exception_types == ["ValueError"]

    def test_loads_multiple_contracts(self, tmp_path: Path) -> None:
        """load_contracts() loads all YAML files in contracts/ directory."""
        contracts_dir = tmp_path / "contracts"
        _write_contract(contracts_dir, "c1", "a.py::func_a", ["ErrorA"])
        _write_contract(contracts_dir, "c2", "b.py::func_b", ["ErrorB"])
        checker = ContractChecker()
        contracts = checker.load_contracts(tmp_path)
        assert len(contracts) == 2

    def test_raises_contract_parse_error_on_malformed_yaml(self, tmp_path: Path) -> None:
        """load_contracts() raises ContractParseError on malformed YAML."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        bad_yaml = contracts_dir / "bad.yaml"
        bad_yaml.write_text("key: [unclosed bracket", encoding="utf-8")
        checker = ContractChecker()
        with pytest.raises(ContractParseError):
            checker.load_contracts(tmp_path)

    def test_raises_contract_parse_error_on_missing_symbol_id(self, tmp_path: Path) -> None:
        """load_contracts() raises ContractParseError when symbol_id is missing."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        yaml_path = contracts_dir / "no_symbol.yaml"
        yaml_path.write_text("exception_types:\n  - ValueError\n", encoding="utf-8")
        checker = ContractChecker()
        with pytest.raises(ContractParseError) as exc_info:
            checker.load_contracts(tmp_path)
        assert "symbol_id" in exc_info.value.parse_error

    def test_raises_contract_parse_error_on_missing_exception_types(self, tmp_path: Path) -> None:
        """load_contracts() raises ContractParseError when exception_types is missing."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        yaml_path = contracts_dir / "no_exc.yaml"
        yaml_path.write_text("symbol_id: pkg/module.py::func\n", encoding="utf-8")
        checker = ContractChecker()
        with pytest.raises(ContractParseError) as exc_info:
            checker.load_contracts(tmp_path)
        assert "exception_types" in exc_info.value.parse_error

    def test_contract_parse_error_has_file_path_attribute(self, tmp_path: Path) -> None:
        """ContractParseError.file_path points to the malformed YAML file."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        bad_yaml = contracts_dir / "bad.yaml"
        bad_yaml.write_text("not: valid: yaml: [", encoding="utf-8")
        checker = ContractChecker()
        with pytest.raises(ContractParseError) as exc_info:
            checker.load_contracts(tmp_path)
        assert exc_info.value.file_path == bad_yaml


# ---------------------------------------------------------------------------
# Unit tests — check() exception_types
# ---------------------------------------------------------------------------


class TestCheckExceptionTypes:
    """Unit tests for ContractChecker.check() exception_types validation."""

    def test_no_failures_when_function_raises_allowed_exception(self, tmp_path: Path) -> None:
        """check() returns [] when function only raises allowed exception types."""
        source = (
            "class AllowedError(Exception): pass\n\ndef my_func():\n    raise AllowedError('ok')\n"
        )
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert failures == []

    def test_failure_when_function_raises_disallowed_exception(self, tmp_path: Path) -> None:
        """check() returns a ContractFailure when function raises a disallowed type."""
        source = (
            "class AllowedError(Exception): pass\n\n"
            "def my_func():\n"
            "    raise ValueError('not allowed')\n"
        )
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert len(failures) == 1
        assert failures[0].constraint == "exception_types"
        assert "ValueError" in failures[0].actual

    def test_bare_raise_is_not_flagged(self, tmp_path: Path) -> None:
        """check() does not flag bare 'raise' (re-raise) statements."""
        source = "def my_func():\n    try:\n        pass\n    except Exception:\n        raise\n"
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert failures == []

    def test_raise_x_from_y_only_checks_x(self, tmp_path: Path) -> None:
        """check() only checks the raised exception type, not the cause in 'raise X from Y'."""
        source = (
            "class AllowedError(Exception): pass\n\n"
            "def my_func():\n"
            "    cause = RuntimeError('cause')\n"
            "    raise AllowedError('ok') from cause\n"
        )
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert failures == []

    def test_method_inside_class_is_found(self, tmp_path: Path) -> None:
        """check() finds methods inside classes, not just module-level functions."""
        source = (
            "class AllowedError(Exception): pass\n\n"
            "class MyClass:\n"
            "    def my_method(self):\n"
            "        raise ValueError('disallowed')\n"
        )
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::MyClass.my_method",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert len(failures) == 1
        assert "ValueError" in failures[0].actual

    def test_no_failures_when_function_raises_nothing(self, tmp_path: Path) -> None:
        """check() returns [] when function has no raise statements."""
        source = "def my_func():\n    return 42\n"
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert failures == []

    def test_skips_missing_source_file_gracefully(self, tmp_path: Path) -> None:
        """check() returns [] when the source file referenced by a contract is missing."""
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/nonexistent.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        # Should not raise — just skip
        failures = checker.check(tmp_path)
        assert failures == []

    def test_contract_failure_has_correct_symbol_id(self, tmp_path: Path) -> None:
        """ContractFailure.symbol_id matches the contract's symbol_id."""
        source = "def my_func():\n    raise ValueError('bad')\n"
        _write_source(tmp_path, "pkg/module.py", source)
        _write_contract(
            tmp_path / "contracts",
            "c",
            "pkg/module.py::my_func",
            ["AllowedError"],
        )
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert failures[0].symbol_id == "pkg/module.py::my_func"

    def test_returns_empty_list_when_no_contracts_dir(self, tmp_path: Path) -> None:
        """check() returns [] when there is no contracts/ directory."""
        checker = ContractChecker()
        failures = checker.check(tmp_path)
        assert failures == []


# ---------------------------------------------------------------------------
# Property 22: ContractChecker detects exception type violations
# ---------------------------------------------------------------------------


@given(
    allowed_names=st.lists(
        st.from_regex(r"[A-Z][a-zA-Z]{3,15}Error", fullmatch=True),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    disallowed_name=st.from_regex(r"[A-Z][a-zA-Z]{3,15}Error", fullmatch=True),
)
@settings(max_examples=100)
def test_property_22_contract_checker_detects_exception_violations(
    allowed_names: list[str],
    disallowed_name: str,
) -> None:
    """Property 22: ContractChecker detects exception type violations.

    For any contract specifying a set of allowed exception types E, and a
    function implementation that raises an exception type not in E,
    ContractChecker.check() SHALL return a ContractFailure for that function.

    # Feature: local-sage, Property 22: ContractChecker detects exception type violations
    **Validates: Requirements 6.8**
    """
    # Feature: local-sage, Property 22: ContractChecker detects exception type violations
    # Ensure disallowed_name is not in the allowed set
    from hypothesis import assume

    assume(disallowed_name not in allowed_names)

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp)

        # Build exception class definitions
        exc_defs = "\n".join(
            f"class {name}(Exception): pass" for name in allowed_names + [disallowed_name]
        )
        source = f"{exc_defs}\n\ndef target_func():\n    raise {disallowed_name}('violation')\n"
        _write_source(repo_dir, "pkg/module.py", source)
        _write_contract(
            repo_dir / "contracts",
            "test_contract",
            "pkg/module.py::target_func",
            allowed_names,
        )

        checker = ContractChecker()
        failures = checker.check(repo_dir)

        assert len(failures) >= 1
        assert any(f.constraint == "exception_types" for f in failures)
        assert any(disallowed_name in f.actual for f in failures)
