"""Contract checker for Layer 6 — Validation.

Provides :class:`ContractChecker`, which loads YAML contract files from a
``contracts/`` directory and performs static analysis to verify that each
contracted symbol honours its declared ``exception_types`` and
``return_shape``.  ``preconditions`` are treated as documentation only in v1
and are logged at INFO level without enforcement.

⚠️  This module is the core novel contribution of local-sage.
    It REQUIRES manual human review before any task that uses it is
    marked complete.
"""

from __future__ import annotations

import ast
import importlib
import logging
import re
import sys
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from local_sage.validation.exceptions import ContractParseError
from local_sage.validation.result import ContractFailure

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AST Helper Classes
# ---------------------------------------------------------------------------


class _FunctionASTVisitor(ast.NodeVisitor):
    """AST visitor to find a specific function by name."""
    
    def __init__(self, function_name: str):
        self.function_name = function_name
        self.function_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == self.function_name:
            self.function_node = node
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name == self.function_name:
            self.function_node = node
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Contract:
    """A single contract loaded from a YAML file.

    Attributes:
        symbol_id: Fully-qualified symbol identifier in the form
            ``"path/to/file.py::ClassName.method"`` or
            ``"path/to/file.py::function_name"``.
        exception_types: Allowed exception class names that the symbol may
            raise.  Any ``Raise`` node whose exception type is not in this
            list is flagged as a :class:`~local_sage.validation.result.ContractFailure`.
        return_shape: Optional dict with a ``"type"`` key whose value is the
            expected return annotation string.  ``None`` means no return-shape
            check is performed.
        preconditions: Human-readable precondition strings.  Treated as
            documentation only in v1 — never evaluated or enforced.
        source_file: Relative path to the source file, resolved from
            ``symbol_id`` during :meth:`ContractChecker.load_contracts`.
        function_name: Function or method name (e.g. ``"OllamaClient.generate"``
            or ``"validate_and_apply"``), resolved from ``symbol_id`` during
            :meth:`ContractChecker.load_contracts`.
    """

    symbol_id: str
    exception_types: list[str]
    return_shape: dict[str, Any] | None
    preconditions: list[str] = field(default_factory=list)
    source_file: Path = field(default_factory=Path)
    function_name: str = ""


# ---------------------------------------------------------------------------
# ContractChecker
# ---------------------------------------------------------------------------


class ContractChecker:
    """Loads YAML contracts and performs static analysis against source code.

    Contract YAML files live at ``<repo_dir>/contracts/*.yaml``.  Each file
    describes a single symbol's allowed exception types, expected return
    annotation, and (documentation-only) preconditions.

    Static analysis strategy:

    - **exception_types**: ``ast.parse()`` the function source, walk ``Raise``
      nodes, extract the exception class name, and compare against the
      contract's allowed list.
    - **return_shape**: Dynamically import the module and call
      ``typing.get_type_hints()`` to retrieve the return annotation, then
      compare its string representation against the contract's ``type`` field.
    - **preconditions**: Logged at INFO level only — not evaluated.

    Example::

        checker = ContractChecker()
        failures = checker.check(Path("/path/to/repo"))
        for f in failures:
            print(f.symbol_id, f.constraint, f.actual)
    """

    def load_contracts(self, contracts_dir: Path) -> list[Contract]:
        """Load all ``*.yaml`` contract files from ``contracts_dir``.

        Parses each file with ``yaml.safe_load()``.  Resolves ``source_file``
        and ``function_name`` from ``symbol_id``.  Logs preconditions at INFO
        level.  Skips the directory gracefully if it does not
        exist.

        Args:
            contracts_dir: Path to the repository's contracts directory.

        Returns:
            A list of :class:`Contract` objects, one per YAML file.

        Raises:
            ContractParseError: If any YAML file is malformed or missing
                required fields (``symbol_id`` or ``exception_types``).
        """
        if not contracts_dir.is_dir():
            logger.info("No contracts/ directory found at %s — skipping", contracts_dir)
            return []

        contracts: list[Contract] = []
        for yaml_path in sorted(contracts_dir.glob("*.yaml")):
            contract = self._parse_yaml_file(yaml_path)
            self._log_preconditions(contract)
            contracts.append(contract)
        return contracts

    def check(self, contracts_dir: Path, source_dir: Path) -> list[ContractFailure]:
        """Run all contract checks against the source code in *source_dir*.

        Loads contracts from *contracts_dir*, then for each contract
        checks ``exception_types`` via AST walking and ``return_shape`` via
        ``typing.get_type_hints()`` against the code in *source_dir*.

        Args:
            contracts_dir: Path to the original repository's contracts directory.
            source_dir: Path to the source code to validate (typically a temp copy).

        Returns:
            A list of :class:`~local_sage.validation.result.ContractFailure`
            objects for every constraint violation found.  An empty list means
            all contracts pass.
        """
        contracts = self.load_contracts(contracts_dir)
        failures: list[ContractFailure] = []
        for contract in contracts:
            failures.extend(self._check_exception_types(contract, source_dir))
            failures.extend(self._check_return_shape(contract, source_dir))
            failures.extend(self._check_preconditions_ast(contract, source_dir))
        return failures

    # ------------------------------------------------------------------
    # Private helpers — each ≤ 40 lines
    # ------------------------------------------------------------------

    def _parse_yaml_file(self, yaml_path: Path) -> Contract:
        """Parse a single YAML contract file into a :class:`Contract`.

        Args:
            yaml_path: Absolute path to the ``.yaml`` file.

        Returns:
            A populated :class:`Contract` dataclass.

        Raises:
            ContractParseError: If the file cannot be parsed or is missing
                required fields.
        """
        raw = self._load_yaml(yaml_path)
        self._validate_required_fields(raw, yaml_path)
        symbol_id = str(raw["symbol_id"])
        source_file, function_name = _resolve_symbol_id(symbol_id)
        return Contract(
            symbol_id=symbol_id,
            exception_types=[str(e) for e in raw.get("exception_types", [])],
            return_shape=raw.get("return_shape") or None,
            preconditions=[str(p) for p in raw.get("preconditions", [])],
            source_file=source_file,
            function_name=function_name,
        )

    def _load_yaml(self, yaml_path: Path) -> dict[str, Any]:
        """Load and parse a YAML file, raising ContractParseError on failure.

        Args:
            yaml_path: Path to the YAML file.

        Returns:
            Parsed YAML contents as a dict.

        Raises:
            ContractParseError: If PyYAML is missing or the file is malformed.
        """
        try:
            import yaml  # PyYAML — transitive dep of mem0ai
        except ImportError as exc:
            raise ContractParseError(
                "PyYAML is not installed; cannot parse contract files.",
                file_path=yaml_path,
                parse_error=str(exc),
            ) from exc
        try:
            raw: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            return raw
        except Exception as exc:  # noqa: BLE001
            raise ContractParseError(
                f"Failed to parse contract file: {yaml_path}",
                file_path=yaml_path,
                parse_error=str(exc),
            ) from exc

    def _validate_required_fields(self, raw: Any, yaml_path: Path) -> None:
        """Raise ContractParseError if required fields are missing.

        Args:
            raw: Parsed YAML value (expected to be a dict).
            yaml_path: Path to the YAML file (for error messages).

        Raises:
            ContractParseError: If ``symbol_id`` or ``exception_types`` is absent.
        """
        if not isinstance(raw, dict) or "symbol_id" not in raw:
            raise ContractParseError(
                f"Contract file missing required 'symbol_id' field: {yaml_path}",
                file_path=yaml_path,
                parse_error="missing 'symbol_id'",
            )
        if "exception_types" not in raw:
            raise ContractParseError(
                f"Contract file missing required 'exception_types' field: {yaml_path}",
                file_path=yaml_path,
                parse_error="missing 'exception_types'",
            )

    def _log_preconditions(self, contract: Contract) -> None:
        """Log preconditions at INFO level (documentation only in v1).

        Args:
            contract: The contract whose preconditions to log.
        """
        for precondition in contract.preconditions:
            logger.info(
                "Contract precondition (not enforced): %s — %s",
                contract.symbol_id,
                precondition,
            )

    def _check_preconditions_ast(self, contract: Contract, repo_dir: Path) -> list[ContractFailure]:
        """Check that the function starts with an assert statement for the preconditions."""
        if not contract.preconditions:
            return []
            
        full_path = repo_dir / contract.source_file
        if not full_path.exists():
            return []
            
        try:
            tree = ast.parse(full_path.read_text(encoding="utf-8"))
            visitor = _FunctionASTVisitor(contract.function_name)
            visitor.visit(tree)
            
            if visitor.function_node:
                first_stmts = visitor.function_node.body[:len(contract.preconditions)]
                for stmt in first_stmts:
                    if not isinstance(stmt, ast.Assert):
                        return [ContractFailure(symbol_id=contract.symbol_id, constraint="preconditions", actual="Function does not start with assert statements for preconditions")]
        except SyntaxError:
            pass
        return []

    def _check_exception_types(self, contract: Contract, repo_dir: Path) -> list[ContractFailure]:
        """Check that all Raise nodes use allowed exception types.

        Args:
            contract: The contract being checked.
            repo_dir: Repository root directory.

        Returns:
            List of ContractFailure objects for exception-type violations.
        """
        if not contract.exception_types:
            return []
        source_path = repo_dir / contract.source_file
        if not source_path.is_file():
            return [
                ContractFailure(
                    symbol_id=contract.symbol_id,
                    constraint="source_file_not_found",
                    actual=str(source_path),
                )
            ]
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            logger.warning("AST parse failed for %s: %s", contract.symbol_id, exc)
            return []
        func_node = self._find_function_node(tree, contract.function_name)
        if func_node is None:
            logger.warning(
                "Function %s not found in AST for %s", contract.function_name, contract.symbol_id
            )
            return []
        return self._collect_raise_failures(contract, func_node)

    def _collect_raise_failures(
        self,
        contract: Contract,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[ContractFailure]:
        """Walk Raise nodes in *func_node* and collect violations.

        Args:
            contract: The contract being checked.
            func_node: The AST function node to walk.

        Returns:
            List of :class:`~local_sage.validation.result.ContractFailure`
            objects for undeclared exception types.
        """
        allowed = set(contract.exception_types)
        failures: list[ContractFailure] = []

        for node in ast.walk(func_node):
            if not isinstance(node, ast.Raise):
                continue
            exc_name = self._extract_raise_name(node)
            if exc_name is not None and exc_name not in allowed:
                failures.append(
                    ContractFailure(
                        symbol_id=contract.symbol_id,
                        constraint="exception_types",
                        actual=f"raises {exc_name!r} which is not in {sorted(allowed)}",
                    )
                )

        return failures

    def _find_function_node(
        self, tree: ast.AST, function_name: str
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        """Find a function or method node in an AST.

        Handles both module-level functions and class methods.  If
        *function_name* contains a ``"."``, it is treated as
        ``"ClassName.method_name"``; otherwise it is a module-level function.

        Args:
            tree: The parsed module AST.
            function_name: ``"ClassName.method_name"`` or ``"function_name"``.

        Returns:
            The matching ``FunctionDef`` or ``AsyncFunctionDef`` node, or
            ``None`` if not found.
        """
        if "." in function_name:
            class_name, method_name = function_name.split(".", 1)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for item in node.body:
                        if (
                            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and item.name == method_name
                        ):
                            return item
            return None

        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == function_name
            ):
                return node
        return None





    def _extract_raise_name(self, node: ast.Raise) -> str | None:
        """Extract the exception class name from a ``Raise`` AST node.

        Handles:
        - Bare ``raise`` (re-raise) → returns ``None`` (skip)
        - ``raise SomeError(...)`` → ``ast.Call`` with ``ast.Name`` func
        - ``raise SomeError`` → ``ast.Name``
        - ``raise module.SomeError(...)`` → ``ast.Call`` with ``ast.Attribute``
        - ``raise X from Y`` → only ``node.exc`` is inspected; ``node.cause``
          is ignored entirely.

        Args:
            node: An ``ast.Raise`` node from the function body.

        Returns:
            The exception class name string, or ``None`` for bare re-raises
            or unrecognised patterns.
        """
        if node.exc is None:
            return None
        exc = node.exc
        if isinstance(exc, ast.Call):
            func = exc.func
            if isinstance(func, ast.Name):
                return func.id
            if isinstance(func, ast.Attribute):
                return func.attr
        if isinstance(exc, ast.Name):
            return exc.id
        if isinstance(exc, ast.Attribute):
            return exc.attr
        return None

    def _check_return_shape(self, contract: Contract, repo_dir: Path) -> list[ContractFailure]:
        """Check that the function's return annotation matches the contract.

        Args:
            contract: The contract being checked.
            repo_dir: Repository root directory.

        Returns:
            List of ContractFailure objects for return-shape violations.
        """
        if not contract.return_shape or "type" not in contract.return_shape:
            return []
        source_path = repo_dir / contract.source_file
        if not source_path.is_file():
            return [
                ContractFailure(
                    symbol_id=contract.symbol_id,
                    constraint="source_file_not_found",
                    actual=str(source_path),
                )
            ]
        expected_type = str(contract.return_shape["type"])
        try:
            func_obj = self._import_function(contract, repo_dir)
            hints = typing.get_type_hints(func_obj)
        except (ImportError, Exception) as exc:  # noqa: BLE001
            return self._import_error_failure(contract, exc)
        return self._compare_return_hint(contract, hints, expected_type)

    def _import_error_failure(
        self, contract: Contract, exc: Exception
    ) -> list[ContractFailure]:
        """Return a ContractFailure for a module import error.

        Args:
            contract: The contract being checked.
            exc: The exception that was raised during import.

        Returns:
            A single-element list with a ContractFailure.
        """
        return [
            ContractFailure(
                symbol_id=contract.symbol_id,
                constraint="return_shape",
                actual=f"could not import module for return shape check: {exc}",
            )
        ]

    def _compare_return_hint(
        self,
        contract: Contract,
        hints: dict[str, Any],
        expected_type: str,
    ) -> list[ContractFailure]:
        """Compare the actual return annotation against the expected type.

        Args:
            contract: The contract being checked.
            hints: Type hints dict from ``typing.get_type_hints()``.
            expected_type: The expected return type name string.

        Returns:
            List of ContractFailure objects (empty if annotation matches).
        """
        return_hint = hints.get("return")
        if return_hint is None:
            return [
                ContractFailure(
                    symbol_id=contract.symbol_id,
                    constraint="return_shape",
                    actual="no return annotation found",
                )
            ]
        actual_name = _annotation_name(return_hint)
        if actual_name != expected_type:
            return [
                ContractFailure(
                    symbol_id=contract.symbol_id,
                    constraint="return_shape",
                    actual=f"return annotation is {actual_name!r}, expected {expected_type!r}",
                )
            ]
        return []

    def _import_function(self, contract: Contract, repo_dir: Path) -> Any:
        """Dynamically import the function or method described by *contract*.

        Args:
            contract: The contract whose symbol to import.
            repo_dir: Repository root directory.

        Returns:
            The callable function or method object.

        Raises:
            ImportError: If the module cannot be imported.
            AttributeError: If the symbol is not found in the module.
        """
        module_path = (
            str(contract.source_file).replace("\\", "/").removesuffix(".py").replace("/", ".")
        )
        str_repo = str(repo_dir)
        inserted = str_repo not in sys.path
        if inserted:
            # Append rather than insert(0) so we never shadow packages that
            # were placed on sys.path earlier (e.g. the project root set by the
            # harness bootstrap).  The project root must stay ahead of fixture
            # paths on every task run, not just the first one.
            sys.path.append(str_repo)
        try:
            module = importlib.import_module(module_path)
        finally:
            if inserted and str_repo in sys.path:
                sys.path.remove(str_repo)
        return self._resolve_callable(module, contract.function_name)

    def _resolve_callable(self, module: Any, function_name: str) -> Any:
        """Resolve a callable from *module* by *function_name*.

        Args:
            module: The imported module object.
            function_name: ``"ClassName.method"`` or ``"function_name"``.

        Returns:
            The callable object.
        """
        if "." in function_name:
            class_name, method_name = function_name.split(".", 1)
            return getattr(getattr(module, class_name), method_name)
        return getattr(module, function_name)

    async def fix_contract_violation(
        self, 
        failure: ContractFailure, 
        source_dir: Path, 
        contracts_dir: Path
    ) -> str | None:
        """Use a language model to fix a contract violation by generating corrected code.
        
        Args:
            failure: The contract failure to fix
            source_dir: Directory containing the source files
            contracts_dir: Directory containing the contract files
            
        Returns:
            The corrected source code as a string, or None if no fix could be generated
        """
        contract = self._find_contract_for_failure(failure, contracts_dir)
        if contract is None:
            return None
            
        original_code = self._read_source_file(contract, source_dir)
        if original_code is None:
            return None
            
        client = await self._get_model_client()
        if client is None:
            return None
            
        return await self._generate_and_apply_fix(failure, contract, original_code, client)

    def _find_contract_for_failure(self, failure: ContractFailure, contracts_dir: Path) -> Contract | None:
        """Find the contract associated with a failure."""
        contracts = self.load_contracts(contracts_dir)
        for contract in contracts:
            if contract.symbol_id == failure.symbol_id:
                return contract
        logger.warning("Contract not found for failure: %s", failure.symbol_id)
        return None

    def _read_source_file(self, contract: Contract, source_dir: Path) -> str | None:
        """Read the source file for a contract."""
        source_file = source_dir / contract.source_file
        if not source_file.exists():
            logger.warning("Source file not found: %s", source_file)
            return None
        try:
            return source_file.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read source file %s: %s", source_file, exc)
            return None

    async def _get_model_client(self) -> Any | None:
        """Get a language model client (provider-agnostic)."""
        try:
            from local_sage.model.client import get_client
            return await get_client()
        except Exception as exc:
            logger.warning("Failed to get model client: %s", exc)
            return None

    async def _generate_and_apply_fix(
        self, 
        failure: ContractFailure, 
        contract: Contract, 
        original_code: str, 
        client: Any
    ) -> str | None:
        """Generate a fix using the model and apply it."""
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(failure, contract, original_code)
        
        try:
            response = await client.generate(user_prompt, system_prompt)
            logger.info("LLM response for %s: %s", failure.symbol_id, response.text[:200])
            return self._apply_search_replace_fix(original_code, response.text)
        except Exception as exc:
            logger.warning("Failed to generate fix with LLM: %s", exc)
            return None

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the model."""
        return """You are a code fixing assistant. Your task is to fix contract violations in Python code.

Rules:
1. You MUST output the corrected code in search-replace format
2. Each fix should be in a block like this:
```search-replace
OLD_CODE_HERE
---
NEW_CODE_HERE
```
3. Be precise - only fix the specific violation mentioned
4. Do not make unnecessary changes to working code
5. Preserve all existing functionality while fixing the contract violation"""

    def _build_user_prompt(self, failure: ContractFailure, contract: Contract, original_code: str) -> str:
        """Build the user prompt for the model."""
        return f"""Fix the following contract violation:

Contract: {failure.symbol_id}
Violation: {failure.constraint}
Details: {failure.actual}

Allowed exception types: {contract.exception_types}
Expected return shape: {contract.return_shape}

Source code to fix:
```python
{original_code}
```

Please provide the fix in search-replace format."""
            
    def _apply_search_replace_fix(self, original_code: str, llm_response: str) -> str | None:
        """Apply search-replace blocks from LLM response to the original code.
        
        Args:
            original_code: The original source code
            llm_response: LLM response containing search-replace blocks
            
        Returns:
            The fixed code or None if no valid fixes were found
        """
        logger.info("LLM full response: %s", llm_response)
        
        matches = self._extract_search_replace_blocks(llm_response)
        if not matches:
            return None
            
        return self._apply_replacements(original_code, matches)

    def _extract_search_replace_blocks(self, llm_response: str) -> list[tuple[str, str]]:
        """Extract search-replace blocks from LLM response."""
        pattern = r'```search-replace\n(.*?)\n---\n(.*?)\n```'
        matches = re.findall(pattern, llm_response, re.DOTALL)
        
        if not matches:
            logger.warning("No search-replace blocks found in LLM response")
            # Try alternative patterns
            alt_pattern = r'```search-replace\n(.*?)\n-+\n(.*?)\n```'
            matches = re.findall(alt_pattern, llm_response, re.DOTALL)
            
        if not matches:
            logger.warning("No search-replace blocks found with alternative pattern")
            
        return matches

    def _apply_replacements(self, original_code: str, matches: list[tuple[str, str]]) -> str | None:
        """Apply replacement matches to the original code."""
        fixed_code = original_code
        
        for old_code, new_code in matches:
            old_code = old_code.strip()
            new_code = new_code.strip()
            
            logger.info("Trying to replace:\n'%s'\nwith:\n'%s'", old_code, new_code)
            
            if self._try_exact_replacement(fixed_code, old_code, new_code):
                fixed_code = fixed_code.replace(old_code, new_code)
                logger.info("Applied fix: replaced %d chars", len(old_code))
            elif self._try_flexible_replacement(fixed_code, old_code, new_code):
                fixed_code = self._apply_flexible_replacement(fixed_code, old_code, new_code)
                logger.info("Applied flexible fix")
            else:
                logger.warning("Could not find old code block in source: %s", old_code[:100])
                
        return fixed_code if fixed_code != original_code else None

    def _try_exact_replacement(self, code: str, old_code: str, new_code: str) -> bool:
        """Try exact string replacement."""
        return old_code in code

    def _try_flexible_replacement(self, code: str, old_code: str, new_code: str) -> bool:
        """Check if flexible replacement is possible (ignoring comments)."""
        lines_to_find = old_code.split('\n')
        source_lines = code.split('\n')
        
        for i in range(len(source_lines) - len(lines_to_find) + 1):
            if self._lines_match_ignoring_comments(source_lines[i:i+len(lines_to_find)], lines_to_find):
                return True
        return False

    def _apply_flexible_replacement(self, code: str, old_code: str, new_code: str) -> str:
        """Apply flexible replacement ignoring trailing comments."""
        lines_to_find = old_code.split('\n')
        source_lines = code.split('\n')
        
        for i in range(len(source_lines) - len(lines_to_find) + 1):
            if self._lines_match_ignoring_comments(source_lines[i:i+len(lines_to_find)], lines_to_find):
                new_lines = source_lines[:i] + new_code.split('\n') + source_lines[i + len(lines_to_find):]
                return '\n'.join(new_lines)
        return code

    def _lines_match_ignoring_comments(self, source_lines: list[str], pattern_lines: list[str]) -> bool:
        """Check if lines match, ignoring trailing comments."""
        if len(source_lines) != len(pattern_lines):
            return False
            
        for source_line, pattern_line in zip(source_lines, pattern_lines):
            # Remove inline comments for comparison
            if '#' in source_line:
                source_clean = source_line[:source_line.find('#')].rstrip()
            else:
                source_clean = source_line
                
            if source_clean.strip() != pattern_line.strip():
                return False
        return True
        return fixed_code if fixed_code != original_code else None


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no state)
# ---------------------------------------------------------------------------


def _resolve_symbol_id(symbol_id: str) -> tuple[Path, str]:
    """Resolve a ``symbol_id`` into ``(source_file, function_name)``.

    The ``symbol_id`` format is ``"<relative_file_path>::<symbol>"``.
    The ``<symbol>`` part is either ``"ClassName.method_name"`` or a bare
    ``"function_name"``.

    Args:
        symbol_id: The symbol identifier string from the contract YAML.

    Returns:
        A 2-tuple of ``(source_file_as_Path, function_name_string)``.
    """
    file_part, _, symbol_part = symbol_id.partition("::")
    return Path(file_part), symbol_part


def _annotation_name(hint: Any) -> str:
    """Return a human-readable name for a type annotation.

    Prefers ``__name__`` (plain classes), falls back to ``str(hint)`` for
    generic aliases and ``typing`` constructs.

    Args:
        hint: A type annotation object from ``typing.get_type_hints()``.

    Returns:
        A string representation of the annotation.
    """
    if hasattr(hint, "__name__"):
        return str(hint.__name__)
    raw = str(hint)
    if raw.startswith("typing."):
        return raw[len("typing.") :]
    return raw
