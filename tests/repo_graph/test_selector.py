"""Unit and property-based tests for ContextSelector (Layer 3 — Repo Graph).

Covers select(), _compute_personalization(), and Property 11 (top-K bound).

**Validates: Requirements 3.5**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo
from local_sage.repo_graph.selector import ContextSelector
from tests.strategies import symbol_info_strategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph(symbols: list[SymbolInfo]) -> SymbolGraph:
    """Return a SymbolGraph populated with *symbols*.

    Args:
        symbols: SymbolInfo instances to add.

    Returns:
        A SymbolGraph containing all provided symbols.
    """
    graph = SymbolGraph()
    for sym in symbols:
        graph.add_symbol(sym)
    return graph


def _make_symbol(
    name: str,
    kind: str = "function",
    file_path: str = "mod.py",
) -> SymbolInfo:
    """Return a minimal SymbolInfo for unit tests.

    Args:
        name: Symbol name.
        kind: Symbol kind.
        file_path: Repository-relative file path.

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


# ---------------------------------------------------------------------------
# Unit tests — select()
# ---------------------------------------------------------------------------


def test_select_returns_empty_list_for_empty_graph() -> None:
    """select() returns an empty list when the graph has no nodes."""
    selector = ContextSelector()
    graph = SymbolGraph()
    result = selector.select("add rate limiter", graph, top_k=5)
    assert result == []


def test_select_returns_at_most_top_k_results() -> None:
    """select() returns no more than top_k symbols."""
    symbols = [_make_symbol(f"func_{i}") for i in range(20)]
    graph = _build_graph(symbols)
    selector = ContextSelector()

    result = selector.select("func", graph, top_k=5)
    assert len(result) <= 5


def test_select_returns_symbol_info_objects() -> None:
    """select() returns SymbolInfo instances, not raw node IDs."""
    symbols = [_make_symbol("alpha"), _make_symbol("beta")]
    graph = _build_graph(symbols)
    selector = ContextSelector()

    result = selector.select("alpha", graph, top_k=10)
    for item in result:
        assert isinstance(item, SymbolInfo)


def test_select_all_results_exist_in_graph() -> None:
    """Every symbol returned by select() exists as a node in the graph."""
    symbols = [_make_symbol(f"sym_{i}") for i in range(10)]
    graph = _build_graph(symbols)
    selector = ContextSelector()

    result = selector.select("sym", graph, top_k=10)
    for sym in result:
        node_id = SymbolGraph._make_id(sym.file_path, sym.name)
        assert graph.get_symbol(node_id) is not None, (
            f"Returned symbol {sym.name!r} not found in graph"
        )


def test_select_with_top_k_zero_returns_empty() -> None:
    """select() with top_k=0 returns an empty list."""
    symbols = [_make_symbol("foo")]
    graph = _build_graph(symbols)
    selector = ContextSelector()

    result = selector.select("foo", graph, top_k=0)
    assert result == []


def test_select_with_matching_task_token_boosts_relevant_symbol() -> None:
    """select() ranks symbols whose names match task tokens higher."""
    symbols = [
        _make_symbol("rate_limiter"),
        _make_symbol("unrelated_util"),
        _make_symbol("another_helper"),
    ]
    graph = _build_graph(symbols)
    selector = ContextSelector()

    result = selector.select("rate limiter", graph, top_k=1)
    assert len(result) == 1
    assert result[0].name == "rate_limiter"


def test_select_with_recency_boost_promotes_recent_symbol() -> None:
    """select() applies recency boost to recently modified symbols."""
    symbols = [_make_symbol("old_func"), _make_symbol("new_func")]
    graph = _build_graph(symbols)
    selector = ContextSelector(recency_factor=10.0)

    new_id = SymbolGraph._make_id(Path("mod.py"), "new_func")
    result = selector.select("something", graph, top_k=1, recent_symbol_ids={new_id})
    assert len(result) == 1
    assert result[0].name == "new_func"


# ---------------------------------------------------------------------------
# Property 11: ContextSelector returns at most top-K results
# ---------------------------------------------------------------------------


@given(
    symbols=st.lists(symbol_info_strategy(), min_size=0, max_size=20),
    task=st.text(min_size=0, max_size=100),
    top_k=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_11_selector_returns_at_most_top_k(
    symbols: list[SymbolInfo],
    task: str,
    top_k: int,
) -> None:
    """Property 11: ContextSelector returns at most top-K results.

    For any task description string and SymbolGraph,
    ContextSelector.select(task, graph, top_k=K) SHALL return a list of at
    most K SymbolInfo objects, and every returned object SHALL exist as a
    node in the graph.

    # Feature: local-sage, Property 11: ContextSelector returns at most top-K results
    **Validates: Requirements 3.5**
    """
    # Feature: local-sage, Property 11: ContextSelector returns at most top-K results
    graph = _build_graph(symbols)
    selector = ContextSelector()

    result = selector.select(task, graph, top_k=top_k)

    # Must not exceed top_k
    assert len(result) <= top_k, f"select() returned {len(result)} results but top_k={top_k}"

    # Every returned symbol must exist in the graph
    for sym in result:
        node_id = SymbolGraph._make_id(sym.file_path, sym.name)
        assert graph.get_symbol(node_id) is not None, (
            f"Returned symbol {sym.name!r} (id={node_id!r}) not found in graph"
        )
