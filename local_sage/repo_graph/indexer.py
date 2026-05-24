"""RepoIndexer — tree-sitter-based Python repository indexer.

Walks a repository, parses every ``.py`` file with tree-sitter, and
populates a :class:`SymbolGraph` with functions, classes, imports, and
call edges.  The index is persisted to ``.sage/index.json`` so that
subsequent warm starts only re-parse files whose mtime has changed.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo

_log = logging.getLogger(__name__)

PY_LANGUAGE: Language = Language(tspython.language())


def _make_parser() -> Parser:
    """Return a fresh tree-sitter Parser configured for Python.

    Returns:
        A ``Parser`` instance ready to parse Python source bytes.
    """
    return Parser(PY_LANGUAGE)


def _walk(node: Node) -> Any:
    """Yield *node* and every descendant in depth-first order.

    Args:
        node: The root ``Node`` to walk.

    Yields:
        Each ``Node`` in the subtree rooted at *node*.
    """
    yield node
    for child in node.children:
        yield from _walk(child)


def _node_text(node: Node, source: bytes) -> str:
    """Extract the UTF-8 text for *node* from *source*.

    Args:
        node: The tree-sitter ``Node`` whose text is needed.
        source: The full source bytes of the file.

    Returns:
        The decoded text slice corresponding to *node*.
    """
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _find_parent_class(node: Node) -> str | None:
    """Walk up the tree to find the enclosing class name, if any.

    Args:
        node: A ``Node`` whose ancestors are searched.

    Returns:
        The class name string, or ``None`` if the node is not inside a class.
    """
    parent = node.parent
    while parent is not None:
        if parent.type == "class_definition":
            name_node = parent.child_by_field_name("name")
            if name_node is not None:
                return name_node.text.decode("utf-8", errors="replace")  # type: ignore[union-attr]
        parent = parent.parent
    return None


class RepoIndexer:
    """Parses a Python repository with tree-sitter and builds a SymbolGraph.

    Example::

        indexer = RepoIndexer()
        graph = indexer.index_repo(Path("/my/project"))
        indexer.save_index(graph, Path("/my/project/.sage/index.json"))

        # Later, on warm start:
        cached = indexer.load_index(Path("/my/project/.sage/index.json"))
        if cached is None:
            cached = indexer.index_repo(Path("/my/project"))
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_repo(self, repo_root: Path) -> SymbolGraph:
        """Walk *repo_root*, parse every ``.py`` file, and return a SymbolGraph.

        Files that cannot be read or that contain tree-sitter parse errors are
        logged and skipped; they never cause this method to raise.

        Args:
            repo_root: Absolute path to the root of the repository.

        Returns:
            A fully populated :class:`SymbolGraph`.
        """
        graph = SymbolGraph()
        parser = _make_parser()
        abs_root = repo_root.resolve()
        for py_file in sorted(abs_root.rglob("*.py")):
            if _should_skip(py_file, abs_root):
                continue
            self._parse_file(py_file, abs_root, parser, graph)
        return graph

    def update_file(self, file_path: Path, graph: SymbolGraph) -> None:
        """Re-parse *file_path* and refresh its nodes/edges in *graph*.

        All existing nodes whose ``file_path`` matches *file_path* are removed
        before the file is re-parsed, so the graph stays consistent.

        Args:
            file_path: Absolute path to the ``.py`` file to re-index.
            graph: The :class:`SymbolGraph` to update in place.
        """
        _remove_file_nodes(file_path, graph)
        repo_root = _infer_repo_root(file_path)
        parser = _make_parser()
        self._parse_file(file_path, repo_root, parser, graph)

    def save_index(
        self,
        graph: SymbolGraph,
        cache_path: Path,
        repo_root: Path | None = None,
    ) -> None:
        """Persist *graph* and per-file mtimes to *cache_path* as JSON.

        The parent directory is created if it does not exist.

        Args:
            graph: The :class:`SymbolGraph` to serialise.
            cache_path: Destination path for the JSON cache file.
            repo_root: Repository root used to resolve relative file paths
                when collecting mtimes.  Defaults to
                ``cache_path.parent.parent`` (i.e. the conventional location
                ``<repo_root>/.sage/index.json``).
        """
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        root = (repo_root if repo_root is not None else cache_path.parent.parent).resolve()
        mtimes = _collect_mtimes(graph, root)
        payload: dict[str, Any] = {
            **graph.to_dict(),
            "mtimes": mtimes,
            "repo_root": root.as_posix(),
        }
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _log.debug("Saved index to %s (%d nodes)", cache_path, len(payload["nodes"]))

    def load_index(self, cache_path: Path) -> SymbolGraph | None:
        """Load a cached :class:`SymbolGraph` from *cache_path*.

        Compares the stored mtime for every indexed file against the current
        filesystem mtime.  Returns ``None`` if any file has changed (the
        caller should then call :meth:`index_repo` to rebuild).

        Args:
            cache_path: Path to the JSON cache file written by :meth:`save_index`.

        Returns:
            The cached :class:`SymbolGraph`, or ``None`` if the cache is
            absent, unreadable, or stale.
        """
        if not cache_path.exists():
            return None
        try:
            raw = cache_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("Cannot read index cache %s: %s", cache_path, exc)
            return None

        repo_root_str: str | None = data.get("repo_root")
        repo_root = Path(repo_root_str) if repo_root_str else cache_path.parent.parent
        stored_mtimes: dict[str, float] = data.get("mtimes", {})
        if _any_mtime_changed(stored_mtimes, repo_root):
            _log.info("Index cache is stale — one or more files changed")
            return None

        graph_data = {k: v for k, v in data.items() if k not in ("mtimes", "repo_root")}
        return SymbolGraph.from_dict(graph_data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_file(
        self,
        file_path: Path,
        repo_root: Path,
        parser: Parser,
        graph: SymbolGraph,
    ) -> None:
        """Parse one ``.py`` file and add its symbols/edges to *graph*.

        Logs and returns silently on ``OSError`` or tree-sitter parse errors.

        Args:
            file_path: Absolute path to the source file.
            repo_root: Repository root used to compute relative node IDs.
            parser: A configured tree-sitter ``Parser``.
            graph: The :class:`SymbolGraph` to populate.
        """
        try:
            source = file_path.read_bytes()
        except OSError as exc:
            _log.warning("Cannot read %s: %s — skipping", file_path, exc)
            return

        tree = parser.parse(source)
        if tree.root_node.has_error:
            _log.warning("Syntax errors in %s — skipping", file_path)
            return

        rel_path = _relative_path(file_path, repo_root)
        _extract_symbols(tree.root_node, source, rel_path, graph)
        _extract_call_edges(tree.root_node, source, rel_path, graph)


# ---------------------------------------------------------------------------
# Module-level helpers (keep each ≤ 40 lines)
# ---------------------------------------------------------------------------


def _should_skip(py_file: Path, repo_root: Path) -> bool:
    """Return ``True`` if *py_file* should be excluded from indexing.

    Skips files inside hidden directories (e.g. ``.git``, ``.venv``).

    Args:
        py_file: Candidate file path.
        repo_root: Repository root for relative comparison.

    Returns:
        ``True`` if the file should be skipped.
    """
    try:
        rel = py_file.relative_to(repo_root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in rel.parts[:-1])


def _relative_path(file_path: Path, repo_root: Path) -> Path:
    """Return *file_path* relative to *repo_root*, or *file_path* itself.

    Args:
        file_path: Absolute path to a source file.
        repo_root: Repository root directory.

    Returns:
        A relative :class:`~pathlib.Path`.
    """
    try:
        return file_path.relative_to(repo_root)
    except ValueError:
        return file_path


def _extract_symbols(
    root: Node,
    source: bytes,
    rel_path: Path,
    graph: SymbolGraph,
) -> None:
    """Extract function, class, and import symbols from *root* into *graph*.

    Args:
        root: The tree-sitter root node of the parsed file.
        source: Raw source bytes of the file.
        rel_path: Repository-relative path used for node IDs.
        graph: The :class:`SymbolGraph` to populate.
    """
    for node in _walk(root):
        if node.type == "function_definition":
            _add_function(node, source, rel_path, graph)
        elif node.type == "class_definition":
            _add_class(node, source, rel_path, graph)
        elif node.type in ("import_statement", "import_from_statement"):
            _add_import(node, source, rel_path, graph)


def _add_function(
    node: Node,
    source: bytes,
    rel_path: Path,
    graph: SymbolGraph,
) -> None:
    """Add a ``function_definition`` node to *graph*.

    If the function is inside a class, the symbol name is prefixed with
    ``ClassName.`` to avoid collisions.

    Args:
        node: A ``function_definition`` tree-sitter node.
        source: Raw source bytes.
        rel_path: Repository-relative file path.
        graph: Target :class:`SymbolGraph`.
    """
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    raw_name = _node_text(name_node, source)
    parent_class = _find_parent_class(node)
    name = f"{parent_class}.{raw_name}" if parent_class else raw_name
    symbol = SymbolInfo(
        name=name,
        kind="function",
        file_path=rel_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        source=_node_text(node, source),
    )
    graph.add_symbol(symbol)


def _add_class(
    node: Node,
    source: bytes,
    rel_path: Path,
    graph: SymbolGraph,
) -> None:
    """Add a ``class_definition`` node to *graph*.

    Args:
        node: A ``class_definition`` tree-sitter node.
        source: Raw source bytes.
        rel_path: Repository-relative file path.
        graph: Target :class:`SymbolGraph`.
    """
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = _node_text(name_node, source)
    symbol = SymbolInfo(
        name=name,
        kind="class",
        file_path=rel_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        source=_node_text(node, source),
    )
    graph.add_symbol(symbol)


def _add_import(
    node: Node,
    source: bytes,
    rel_path: Path,
    graph: SymbolGraph,
) -> None:
    """Add an import symbol to *graph* and record import edges.

    Handles both ``import X`` and ``from X import Y`` forms.

    Args:
        node: An ``import_statement`` or ``import_from_statement`` node.
        source: Raw source bytes.
        rel_path: Repository-relative file path.
        graph: Target :class:`SymbolGraph`.
    """
    import_text = _node_text(node, source).strip()
    # Use the full import text as the symbol name (truncated for readability)
    name = import_text.split("\n")[0][:120]
    symbol = SymbolInfo(
        name=name,
        kind="import",
        file_path=rel_path,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        source=import_text,
    )
    graph.add_symbol(symbol)
    _add_import_edges(node, source, rel_path, name, graph)


def _add_import_edges(
    node: Node,
    source: bytes,
    rel_path: Path,
    from_name: str,
    graph: SymbolGraph,
) -> None:
    """Add ``"imports"`` edges from the import symbol to referenced modules.

    Args:
        node: The import tree-sitter node.
        source: Raw source bytes.
        rel_path: Repository-relative file path.
        from_name: The symbol name of the import node (used as edge source).
        graph: Target :class:`SymbolGraph`.
    """
    from_id = f"{rel_path.as_posix()}::{from_name}"
    for child in _walk(node):
        if child.type in ("dotted_name", "identifier") and child.parent == node:
            target_name = _node_text(child, source)
            to_id = f"<module>::{target_name}"
            graph.add_edge(from_id, to_id, "imports")


def _extract_call_edges(
    root: Node,
    source: bytes,
    rel_path: Path,
    graph: SymbolGraph,
) -> None:
    """Add ``"calls"`` edges for every ``call`` node found under *root*.

    The edge runs from the enclosing function (if any) to the callee.

    Args:
        root: The tree-sitter root node of the parsed file.
        source: Raw source bytes.
        rel_path: Repository-relative file path.
        graph: Target :class:`SymbolGraph`.
    """
    for node in _walk(root):
        if node.type != "call":
            continue
        callee_name = _callee_name(node, source)
        if callee_name is None:
            continue
        caller_id = _enclosing_function_id(node, source, rel_path)
        if caller_id is None:
            continue
        to_id = f"{rel_path.as_posix()}::{callee_name}"
        graph.add_edge(caller_id, to_id, "calls")


def _callee_name(node: Node, source: bytes) -> str | None:
    """Extract the callee name from a ``call`` node.

    Handles simple names (``foo()``) and attribute access (``obj.method()``).

    Args:
        node: A ``call`` tree-sitter node.
        source: Raw source bytes.

    Returns:
        The callee name string, or ``None`` if it cannot be determined.
    """
    func_node = node.child_by_field_name("function")
    if func_node is None:
        return None
    if func_node.type == "identifier":
        return _node_text(func_node, source)
    if func_node.type == "attribute":
        attr = func_node.child_by_field_name("attribute")
        if attr is not None:
            return _node_text(attr, source)
    return None


def _enclosing_function_id(
    node: Node,
    source: bytes,
    rel_path: Path,
) -> str | None:
    """Return the symbol ID of the innermost enclosing function, if any.

    Args:
        node: A tree-sitter node whose ancestors are searched.
        source: Raw source bytes.
        rel_path: Repository-relative file path.

    Returns:
        A symbol ID string, or ``None`` if the node is not inside a function.
    """
    parent = node.parent
    while parent is not None:
        if parent.type == "function_definition":
            name_node = parent.child_by_field_name("name")
            if name_node is None:
                return None
            raw_name = _node_text(name_node, source)
            cls = _find_parent_class(parent)
            name = f"{cls}.{raw_name}" if cls else raw_name
            return f"{rel_path.as_posix()}::{name}"
        parent = parent.parent
    return None


def _remove_file_nodes(file_path: Path, graph: SymbolGraph) -> None:
    """Remove all nodes in *graph* whose ``file_path`` matches *file_path*.

    Handles both absolute and relative stored paths by comparing resolved
    absolute paths when possible, and falling back to suffix matching.

    Args:
        file_path: The file whose symbols should be removed (may be absolute).
        graph: The :class:`SymbolGraph` to mutate.
    """
    to_remove: list[str] = []
    abs_target = file_path.resolve() if file_path.is_absolute() else file_path
    for node_id in list(graph._graph.nodes):  # noqa: SLF001
        symbol = graph.get_symbol(node_id)
        if symbol is None:
            continue
        stored = Path(symbol.file_path)
        # Direct match (both relative, or both absolute)
        if stored == abs_target:
            to_remove.append(node_id)
            continue
        # Absolute target vs relative stored: check if target ends with stored
        if file_path.is_absolute() and not stored.is_absolute():
            try:
                if file_path.resolve().parts[-len(stored.parts) :] == stored.parts:
                    to_remove.append(node_id)
            except (ValueError, IndexError):
                pass
    for node_id in to_remove:
        graph._graph.remove_node(node_id)  # noqa: SLF001


def _infer_repo_root(file_path: Path) -> Path:
    """Walk up from *file_path* to find the nearest ``.git`` directory.

    Falls back to the file's parent directory if no ``.git`` is found.

    Args:
        file_path: Absolute path to a source file.

    Returns:
        The inferred repository root :class:`~pathlib.Path`.
    """
    candidate = file_path.parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    return file_path.parent


def _collect_mtimes(graph: SymbolGraph, repo_root: Path | None = None) -> dict[str, float]:
    """Build a ``{posix_path: mtime}`` dict for all files in *graph*.

    Args:
        graph: The :class:`SymbolGraph` whose file paths are inspected.
        repo_root: Optional root used to resolve relative paths to absolute
            ones before calling ``stat()``.

    Returns:
        A mapping from POSIX path string to ``st_mtime`` float.
    """
    mtimes: dict[str, float] = {}
    for node_id in graph._graph.nodes:  # noqa: SLF001
        symbol = graph.get_symbol(node_id)
        if symbol is None:
            continue
        p = Path(symbol.file_path)
        if repo_root is not None and not p.is_absolute():
            p = repo_root / p
        key = Path(symbol.file_path).as_posix()
        if key not in mtimes:
            with contextlib.suppress(OSError):
                mtimes[key] = p.stat().st_mtime
    return mtimes


def _any_mtime_changed(stored: dict[str, float], repo_root: Path | None = None) -> bool:
    """Return ``True`` if any file's current mtime differs from *stored*.

    Args:
        stored: Mapping of POSIX path → stored mtime float.
        repo_root: Optional root used to resolve relative paths.

    Returns:
        ``True`` if at least one file has a different mtime.
    """
    for posix_path, stored_mtime in stored.items():
        p = Path(posix_path)
        if repo_root is not None and not p.is_absolute():
            p = repo_root / p
        try:
            current = p.stat().st_mtime
        except OSError:
            return True
        if current != stored_mtime:
            return True
    return False
