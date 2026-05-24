"""ImpactAnalyzer for Layer 3 — Repo Graph.

Parses a unified diff patch to determine which symbols are directly modified,
then performs a reverse BFS on the SymbolGraph to find all transitively
affected callers and importers.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo


@dataclass
class ImpactReport:
    """Result of an impact analysis on a unified diff patch.

    Attributes:
        directly_modified: Symbols whose source file appears in the patch.
        transitively_affected: Symbols that call or import a directly modified
            symbol, or transitively depend on one (via reverse BFS).
        affected_files: Union of file paths from both lists, deduplicated.
    """

    directly_modified: list[SymbolInfo] = field(default_factory=list)
    transitively_affected: list[SymbolInfo] = field(default_factory=list)
    affected_files: list[Path] = field(default_factory=list)


class ImpactAnalyzer:
    """Determines which symbols and files are affected by a proposed patch.

    Given a unified diff and a populated ``SymbolGraph``, the analyzer:

    1. Parses ``+++ b/<file>`` lines to identify modified files.
    2. Finds all graph nodes whose ``file_path`` matches a modified file
       (``directly_modified``).
    3. Performs a reverse BFS from each directly modified node, following
       predecessor edges (callers / importers) to collect
       ``transitively_affected`` symbols.
    4. Returns an ``ImpactReport`` with both lists and the union of their
       file paths.

    Example::

        analyzer = ImpactAnalyzer()
        report = analyzer.analyze(patch_text, symbol_graph)
        print(report.affected_files)
    """

    def analyze(self, patch: str, graph: SymbolGraph) -> ImpactReport:
        """Analyze *patch* against *graph* and return an ``ImpactReport``.

        Args:
            patch: A unified diff string (output of ``git diff`` or similar).
            graph: A populated ``SymbolGraph`` for the repository.

        Returns:
            An ``ImpactReport`` describing directly modified symbols,
            transitively affected symbols, and all affected file paths.
        """
        modified_files = _parse_modified_files(patch)
        directly_modified = _find_directly_modified(modified_files, graph)
        directly_modified_ids = {_symbol_node_id(sym) for sym in directly_modified}
        transitively_affected = _reverse_bfs(directly_modified_ids, graph, directly_modified_ids)
        affected_files = _collect_affected_files(directly_modified, transitively_affected)
        return ImpactReport(
            directly_modified=directly_modified,
            transitively_affected=transitively_affected,
            affected_files=affected_files,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_modified_files(patch: str) -> set[Path]:
    """Extract modified file paths from a unified diff string.

    Scans for lines starting with ``+++ b/`` and strips the ``b/`` prefix
    to obtain repo-relative paths.

    Args:
        patch: Unified diff text.

    Returns:
        A set of ``Path`` objects for each modified file found in the patch.
    """
    paths: set[Path] = set()
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            raw = line[len("+++ b/") :]
            paths.add(Path(raw))
    return paths


def _find_directly_modified(
    modified_files: set[Path],
    graph: SymbolGraph,
) -> list[SymbolInfo]:
    """Return all graph symbols whose ``file_path`` is in *modified_files*.

    Args:
        modified_files: Set of repo-relative ``Path`` objects from the patch.
        graph: The ``SymbolGraph`` to search.

    Returns:
        A list of ``SymbolInfo`` objects for every matching node.
    """
    result: list[SymbolInfo] = []
    for node_id in graph._graph.nodes():  # noqa: SLF001
        symbol = graph.get_symbol(node_id)
        if symbol is None:
            continue
        if Path(symbol.file_path) in modified_files:
            result.append(symbol)
    return result


def _reverse_bfs(
    start_ids: set[str],
    graph: SymbolGraph,
    exclude_ids: set[str],
) -> list[SymbolInfo]:
    """Collect all symbols reachable via reverse BFS from *start_ids*.

    Follows predecessor edges (incoming ``calls`` and ``imports`` edges) in
    the underlying ``nx.DiGraph``.  Nodes in *exclude_ids* are never added
    to the result (they are the directly modified set).

    Args:
        start_ids: Node IDs to start the BFS from.
        graph: The ``SymbolGraph`` whose predecessors are traversed.
        exclude_ids: Node IDs to skip (typically the directly modified set).

    Returns:
        A list of ``SymbolInfo`` objects for all transitively reachable nodes,
        in BFS order, excluding nodes in *exclude_ids*.
    """
    visited: set[str] = set(start_ids)
    queue: deque[str] = deque(start_ids)
    result: list[SymbolInfo] = []

    while queue:
        current_id = queue.popleft()
        for predecessor_id in graph._graph.predecessors(current_id):  # noqa: SLF001
            if predecessor_id in visited:
                continue
            visited.add(predecessor_id)
            symbol = graph.get_symbol(predecessor_id)
            if symbol is not None and predecessor_id not in exclude_ids:
                result.append(symbol)
            queue.append(predecessor_id)

    return result


def _collect_affected_files(
    directly_modified: list[SymbolInfo],
    transitively_affected: list[SymbolInfo],
) -> list[Path]:
    """Return deduplicated file paths from both symbol lists.

    Args:
        directly_modified: Symbols directly touched by the patch.
        transitively_affected: Symbols transitively affected by the patch.

    Returns:
        A sorted list of unique ``Path`` objects covering all affected files.
    """
    seen: set[Path] = set()
    for sym in directly_modified + transitively_affected:
        seen.add(Path(sym.file_path))
    return sorted(seen)


def _symbol_node_id(symbol: SymbolInfo) -> str:
    """Reconstruct the node ID for *symbol* using the graph's ID convention.

    Args:
        symbol: A ``SymbolInfo`` whose node ID is needed.

    Returns:
        A string of the form ``"<posix_file_path>::<name>"``.
    """
    return f"{Path(symbol.file_path).as_posix()}::{symbol.name}"
