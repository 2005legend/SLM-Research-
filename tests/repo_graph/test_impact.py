"""Unit and property-based tests for ImpactAnalyzer (Layer 3 — Repo Graph).

Covers analyze(), patch parsing, reverse BFS, and Property 12 (transitive
callers).

**Validates: Requirements 3.6**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings

from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo
from local_sage.repo_graph.impact import ImpactAnalyzer, ImpactReport
from tests.strategies import symbol_info_strategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_symbol(
    name: str,
    file_path: str = "mod.py",
    kind: str = "function",
) -> SymbolInfo:
    """Return a minimal SymbolInfo for unit tests.

    Args:
        name: Symbol name.
        file_path: Repository-relative file path.
        kind: Symbol kind.

    Returns:
        A SymbolInfo with sensible defaults.
    """
    return SymbolInfo(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        file_path=Path(file_path),
        start_byte=0,
        end_byte=30,
        start_line=1,
        end_line=3,
        source=f"def {name}(): pass",
    )


def _make_patch(file_path: str) -> str:
    """Return a minimal unified diff patch that modifies *file_path*.

    Args:
        file_path: Repository-relative path to include in the patch header.

    Returns:
        A unified diff string targeting the given file.
    """
    return f"--- a/{file_path}\n+++ b/{file_path}\n@@ -1,1 +1,1 @@\n-old_line\n+new_line\n"


def _build_graph_with_call(
    caller_name: str,
    callee_name: str,
    caller_file: str = "caller.py",
    callee_file: str = "callee.py",
) -> SymbolGraph:
    """Return a SymbolGraph where *caller_name* calls *callee_name*.

    The edge direction follows the graph convention: caller → callee.
    ImpactAnalyzer performs a reverse BFS, so modifying the callee should
    surface the caller as transitively affected.

    Args:
        caller_name: Name of the calling symbol.
        callee_name: Name of the called symbol.
        caller_file: File path for the caller.
        callee_file: File path for the callee.

    Returns:
        A SymbolGraph with one "calls" edge from caller to callee.
    """
    graph = SymbolGraph()
    caller = _make_symbol(caller_name, caller_file)
    callee = _make_symbol(callee_name, callee_file)
    graph.add_symbol(caller)
    graph.add_symbol(callee)

    caller_id = SymbolGraph._make_id(Path(caller_file), caller_name)
    callee_id = SymbolGraph._make_id(Path(callee_file), callee_name)
    graph.add_edge(caller_id, callee_id, "calls")
    return graph


# ---------------------------------------------------------------------------
# Unit tests — analyze()
# ---------------------------------------------------------------------------


def test_analyze_returns_impact_report() -> None:
    """analyze() returns an ImpactReport instance."""
    graph = SymbolGraph()
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze("", graph)
    assert isinstance(report, ImpactReport)


def test_analyze_empty_patch_produces_empty_report() -> None:
    """analyze() with an empty patch returns empty directly_modified and transitively_affected."""
    graph = SymbolGraph()
    sym = _make_symbol("foo", "mod.py")
    graph.add_symbol(sym)

    analyzer = ImpactAnalyzer()
    report = analyzer.analyze("", graph)

    assert report.directly_modified == []
    assert report.transitively_affected == []
    assert report.affected_files == []


def test_analyze_identifies_directly_modified_symbol() -> None:
    """analyze() includes symbols from the patched file in directly_modified."""
    graph = SymbolGraph()
    sym = _make_symbol("my_func", "src/utils.py")
    graph.add_symbol(sym)

    patch = _make_patch("src/utils.py")
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    names = [s.name for s in report.directly_modified]
    assert "my_func" in names


def test_analyze_includes_transitive_caller() -> None:
    """analyze() includes the caller in transitively_affected when the callee is patched."""
    graph = _build_graph_with_call(
        caller_name="caller_func",
        callee_name="callee_func",
        caller_file="caller.py",
        callee_file="callee.py",
    )
    patch = _make_patch("callee.py")
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    transitive_names = [s.name for s in report.transitively_affected]
    assert "caller_func" in transitive_names, (
        f"Expected 'caller_func' in transitively_affected, got: {transitive_names}"
    )


def test_analyze_directly_modified_not_in_transitively_affected() -> None:
    """Directly modified symbols are not duplicated in transitively_affected."""
    graph = _build_graph_with_call(
        caller_name="a",
        callee_name="b",
        caller_file="a.py",
        callee_file="b.py",
    )
    patch = _make_patch("b.py")
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    direct_names = {s.name for s in report.directly_modified}
    transitive_names = {s.name for s in report.transitively_affected}
    overlap = direct_names & transitive_names
    assert overlap == set(), f"Symbols appear in both lists: {overlap}"


def test_analyze_affected_files_is_union_of_both_lists() -> None:
    """affected_files contains paths from both directly_modified and transitively_affected."""
    graph = _build_graph_with_call(
        caller_name="caller",
        callee_name="callee",
        caller_file="caller.py",
        callee_file="callee.py",
    )
    patch = _make_patch("callee.py")
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    affected_posix = {p.as_posix() for p in report.affected_files}
    assert "callee.py" in affected_posix
    assert "caller.py" in affected_posix


def test_analyze_multi_hop_transitive_callers() -> None:
    """analyze() follows transitive chains: A calls B calls C; patching C surfaces A and B."""
    graph = SymbolGraph()
    a = _make_symbol("a", "a.py")
    b = _make_symbol("b", "b.py")
    c = _make_symbol("c", "c.py")
    graph.add_symbol(a)
    graph.add_symbol(b)
    graph.add_symbol(c)

    id_a = SymbolGraph._make_id(Path("a.py"), "a")
    id_b = SymbolGraph._make_id(Path("b.py"), "b")
    id_c = SymbolGraph._make_id(Path("c.py"), "c")
    graph.add_edge(id_a, id_b, "calls")
    graph.add_edge(id_b, id_c, "calls")

    patch = _make_patch("c.py")
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    transitive_names = {s.name for s in report.transitively_affected}
    assert "b" in transitive_names
    assert "a" in transitive_names


def test_analyze_patch_with_no_matching_files_returns_empty() -> None:
    """analyze() returns empty lists when the patch references no files in the graph."""
    graph = SymbolGraph()
    sym = _make_symbol("foo", "real.py")
    graph.add_symbol(sym)

    patch = _make_patch("other.py")
    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    assert report.directly_modified == []
    assert report.transitively_affected == []


# ---------------------------------------------------------------------------
# Property 12: ImpactAnalyzer includes transitive callers
# ---------------------------------------------------------------------------


@given(
    caller=symbol_info_strategy(),
    callee=symbol_info_strategy(),
)
@settings(max_examples=100)
def test_property_12_impact_includes_transitive_callers(
    caller: SymbolInfo,
    callee: SymbolInfo,
) -> None:
    """Property 12: ImpactAnalyzer includes transitive callers.

    For any SymbolGraph where symbol B has an incoming "calls" edge from
    symbol A, and a patch that modifies symbol A's file, ImpactAnalyzer.analyze()
    SHALL include symbol B in ImpactReport.transitively_affected.

    Here we model: caller (A) calls callee (B). We patch callee's file.
    The reverse BFS from callee should surface caller as transitively affected.

    # Feature: local-sage, Property 12: ImpactAnalyzer includes transitive callers
    **Validates: Requirements 3.6**
    """
    # Feature: local-sage, Property 12: ImpactAnalyzer includes transitive callers

    # Skip degenerate case where caller and callee share the same node ID
    caller_id = SymbolGraph._make_id(caller.file_path, caller.name)
    callee_id = SymbolGraph._make_id(callee.file_path, callee.name)
    if caller_id == callee_id:
        return

    # Skip case where caller and callee are in the same file: patching that
    # file makes the caller directly_modified, so it is excluded from
    # transitively_affected by design (no duplication between the two lists).
    if Path(caller.file_path).as_posix() == Path(callee.file_path).as_posix():
        return

    graph = SymbolGraph()
    graph.add_symbol(caller)
    graph.add_symbol(callee)
    graph.add_edge(caller_id, callee_id, "calls")

    # Patch the callee's file
    callee_posix = Path(callee.file_path).as_posix()
    patch = f"--- a/{callee_posix}\n+++ b/{callee_posix}\n@@ -1,1 +1,1 @@\n-old\n+new\n"

    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(patch, graph)

    # callee must be directly modified
    direct_names = {s.name for s in report.directly_modified}
    assert callee.name in direct_names, (
        f"Expected callee {callee.name!r} in directly_modified, got: {direct_names}"
    )

    # caller must be transitively affected (it calls the modified callee)
    transitive_names = {s.name for s in report.transitively_affected}
    assert caller.name in transitive_names, (
        f"Expected caller {caller.name!r} in transitively_affected, got: {transitive_names}"
    )
