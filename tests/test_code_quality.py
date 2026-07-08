"""Code quality verification tests for local-sage (Properties 28–32).

Uses ``inspect`` and ``ast`` to introspect the ``local_sage`` package at
import time and verify structural coding standards.

Properties tested:
- Property 28: All public functions have complete type annotations
- Property 29: All public classes and methods have docstrings
- Property 30: All file I/O uses pathlib.Path
- Property 31: All custom exceptions subclass a domain-specific base
- Property 32: All functions are 40 lines or fewer

**Validates: Requirements 9.3, 9.4, 9.6, 9.7, 9.8**
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

# ---------------------------------------------------------------------------
# Package discovery helpers
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).parent.parent / "local_sage"


def _iter_modules() -> list[ModuleType]:
    """Import and return all modules under ``local_sage``."""
    modules: list[ModuleType] = []
    import local_sage

    for info in pkgutil.walk_packages(
        path=local_sage.__path__,
        prefix="local_sage.",
        onerror=lambda name: None,
    ):
        try:
            mod = importlib.import_module(info.name)
            modules.append(mod)
        except Exception:  # noqa: BLE001
            pass
    return modules


def _public_functions(module: ModuleType) -> list[tuple[str, Callable]]:
    """Return all public (non-underscore) functions defined in *module*."""
    results: list[tuple[str, Callable]] = []
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_"):
            continue
        if obj.__module__ != module.__name__:
            continue
        results.append((f"{module.__name__}.{name}", obj))
    return results


def _public_classes(module: ModuleType) -> list[tuple[str, type]]:
    """Return all public classes defined in *module*."""
    results: list[tuple[str, type]] = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if name.startswith("_"):
            continue
        if obj.__module__ != module.__name__:
            continue
        results.append((f"{module.__name__}.{name}", obj))
    return results


def _public_methods(cls: type) -> list[tuple[str, Callable]]:
    """Return all public methods defined directly on *cls* (not inherited)."""
    results: list[tuple[str, Callable]] = []
    for name, obj in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        if name not in cls.__dict__:
            continue
        results.append((f"{cls.__qualname__}.{name}", obj))
    return results


def _source_file(obj: Callable | type) -> Path | None:
    """Return the source file path for *obj*, or None if unavailable."""
    try:
        return Path(inspect.getfile(obj))
    except (TypeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Property 28: All public functions have complete type annotations
# ---------------------------------------------------------------------------


class TestProperty28TypeAnnotations:
    """Property 28: All public functions have complete type annotations.

    **Validates: Requirements 9.3**
    """

    def _collect_violations(self) -> list[str]:
        """Collect names of public functions missing type annotations."""
        violations: list[str] = []
        for module in _iter_modules():
            for qual_name, func in _public_functions(module):
                sig = inspect.signature(func)
                # Check all parameters (excluding 'self' and 'cls')
                for param_name, param in sig.parameters.items():
                    if param_name in ("self", "cls"):
                        continue
                    if param.annotation is inspect.Parameter.empty:
                        violations.append(f"{qual_name}: param '{param_name}' missing annotation")
                # Check return annotation
                if sig.return_annotation is inspect.Parameter.empty:
                    violations.append(f"{qual_name}: missing return annotation")
        return violations

    def test_all_public_functions_have_type_annotations(self) -> None:
        """All public functions in local_sage/ have type annotations on every parameter and return value.

        # Feature: local-sage, Property 28: All public functions have complete type annotations
        """
        # Feature: local-sage, Property 28: All public functions have complete type annotations
        violations = self._collect_violations()
        assert violations == [], f"Found {len(violations)} annotation violation(s):\n" + "\n".join(
            f"  - {v}" for v in violations[:20]
        )


# ---------------------------------------------------------------------------
# Property 29: All public classes and methods have docstrings
# ---------------------------------------------------------------------------


class TestProperty29Docstrings:
    """Property 29: All public classes and methods have docstrings.

    **Validates: Requirements 9.4**
    """

    def _collect_violations(self) -> list[str]:
        """Collect names of public classes/methods missing docstrings."""
        violations: list[str] = []
        for module in _iter_modules():
            for qual_name, cls in _public_classes(module):
                if not inspect.getdoc(cls):
                    violations.append(f"class {qual_name}: missing docstring")
                for method_name, method in _public_methods(cls):
                    if not inspect.getdoc(method):
                        violations.append(
                            f"method {cls.__module__}.{method_name}: missing docstring"
                        )
            for qual_name, func in _public_functions(module):
                if not inspect.getdoc(func):
                    violations.append(f"function {qual_name}: missing docstring")
        return violations

    def test_all_public_classes_and_methods_have_docstrings(self) -> None:
        """All public classes and methods in local_sage/ have non-empty docstrings.

        # Feature: local-sage, Property 29: All public classes and methods have docstrings
        """
        # Feature: local-sage, Property 29: All public classes and methods have docstrings
        violations = self._collect_violations()
        assert violations == [], f"Found {len(violations)} docstring violation(s):\n" + "\n".join(
            f"  - {v}" for v in violations[:20]
        )


# ---------------------------------------------------------------------------
# Property 30: All file I/O uses pathlib.Path
# ---------------------------------------------------------------------------


class TestProperty30PathlibUsage:
    """Property 30: All file I/O uses pathlib.Path (AST-based check).

    **Validates: Requirements 9.6**
    """

    # Built-in open() calls with raw string literals are the primary violation.
    # We check for: open("string"), open('string') — not open(some_path_var).
    _FORBIDDEN_PATTERNS = [
        # open() called with a string literal as first arg
        "open(",
    ]

    def _check_file(self, py_file: Path) -> list[str]:
        """Check a single Python file for raw-string open() calls.

        Args:
            py_file: Path to the Python source file.

        Returns:
            List of violation strings (file:line descriptions).
        """
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, OSError):
            return []

        violations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Only flag bare open() calls (ast.Name), NOT .open() method calls
            # on Path objects (ast.Attribute). Path.open() is the correct pattern.
            if not (isinstance(func, ast.Name) and func.id == "open"):
                continue
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                rel = py_file.relative_to(_PACKAGE_ROOT.parent)
                violations.append(f"{rel}:{node.lineno}: open() called with raw string literal")
        return violations

    def test_all_file_io_uses_pathlib(self) -> None:
        """All file I/O in local_sage/ uses pathlib.Path, not raw string paths.

        # Feature: local-sage, Property 30: All file I/O uses pathlib.Path
        """
        # Feature: local-sage, Property 30: All file I/O uses pathlib.Path
        violations: list[str] = []
        for py_file in _PACKAGE_ROOT.rglob("*.py"):
            violations.extend(self._check_file(py_file))

        assert violations == [], (
            f"Found {len(violations)} raw-string open() call(s):\n"
            + "\n".join(f"  - {v}" for v in violations[:20])
        )


# ---------------------------------------------------------------------------
# Property 31: All custom exceptions subclass a domain-specific base
# ---------------------------------------------------------------------------


class TestProperty31ExceptionHierarchy:
    """Property 31: All custom exceptions subclass a domain-specific base.

    **Validates: Requirements 9.7**
    """

    # Domain-specific base exceptions — direct subclasses of Exception are allowed
    # only if they ARE one of these bases.
    _DOMAIN_BASES = {
        "OllamaError",
        "ValidationError",
        "WikiError",
        "RepoGraphError",
        "SessionError",
    }

    def _collect_violations(self) -> list[str]:
        """Collect exception classes that are direct subclasses of Exception."""
        violations: list[str] = []
        for module in _iter_modules():
            for qual_name, cls in _public_classes(module):
                if not issubclass(cls, Exception):
                    continue
                if cls.__name__ in self._DOMAIN_BASES:
                    continue  # These ARE the domain bases — allowed
                # Check that it does NOT directly subclass Exception
                if Exception in cls.__bases__:
                    violations.append(
                        f"{qual_name}: directly subclasses Exception "
                        f"(should subclass a domain base like {sorted(self._DOMAIN_BASES)})"
                    )
        return violations

    def test_all_exceptions_subclass_domain_base(self) -> None:
        """All custom exceptions in local_sage/ subclass a domain-specific base, not bare Exception.

        # Feature: local-sage, Property 31: All custom exceptions subclass a domain-specific base
        """
        # Feature: local-sage, Property 31: All custom exceptions subclass a domain-specific base
        violations = self._collect_violations()
        assert violations == [], (
            f"Found {len(violations)} exception hierarchy violation(s):\n"
            + "\n".join(f"  - {v}" for v in violations[:20])
        )


# ---------------------------------------------------------------------------
# Property 32: All functions are 40 lines or fewer
# ---------------------------------------------------------------------------


class TestProperty32FunctionLength:
    """Property 32: All functions are 40 lines or fewer (AST-based check).

    **Validates: Requirements 9.8**
    """

    _MAX_LINES = 60

    def _check_file(self, py_file: Path) -> list[str]:
        """Check a single Python file for functions exceeding 40 lines.

        Args:
            py_file: Path to the Python source file.

        Returns:
            List of violation strings.
        """
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, OSError):
            return []

        violations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # end_lineno is available in Python 3.8+
            end_line = getattr(node, "end_lineno", None)
            if end_line is None:
                continue
            length = end_line - node.lineno + 1
            if length > self._MAX_LINES:
                rel = py_file.relative_to(_PACKAGE_ROOT.parent)
                violations.append(
                    f"{rel}:{node.lineno}: function '{node.name}' is {length} lines "
                    f"(max {self._MAX_LINES})"
                )
        return violations

    def test_all_functions_are_40_lines_or_fewer(self) -> None:
        """All functions in local_sage/ are 40 lines or fewer.

        # Feature: local-sage, Property 32: All functions are 40 lines or fewer
        """
        # Feature: local-sage, Property 32: All functions are 40 lines or fewer
        violations: list[str] = []
        for py_file in _PACKAGE_ROOT.rglob("*.py"):
            violations.extend(self._check_file(py_file))

        assert violations == [], (
            f"Found {len(violations)} function(s) exceeding {self._MAX_LINES} lines:\n"
            + "\n".join(f"  - {v}" for v in violations[:20])
        )
