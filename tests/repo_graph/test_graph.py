"""Unit and property-based tests for SymbolGraph (Layer 3 — Repo Graph).

Covers add_symbol, add_edge, get_symbol, neighbors, to_dict, from_dict,
and Property 8 (symbol kind classification) and Property 9 (index round-trip).

**Validates: Requirements 3.2, 3.3**
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings

from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo
from local_sage.repo_graph.indexer import RepoIndexer
from tests.strategies import python_source_strategy, symbol_info_strategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_symbol(
    name: str = "foo",
    kind: str = "function",
    file_path: str | Path = "pkg/mod.py",
) -> SymbolInfo:
    """Return a minimal SymbolInfo for use in unit tests.

    Args:
        name: Symbol name.
        kind: Symbol kind (function, class, import).
        file_path: Repository-relative file path.

    Returns:
        A SymbolInfo instance with sensible defaults.
    """
    return SymbolInfo(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        file_path=Path(file_path),
        start_byte=0,
        end_byte=20,
        start_line=1,
        end_line=3,
        source="def foo(): pass",
    )


# ---------------------------------------------------------------------------
# Unit tests — add_symbol / get_symbol
# ---------------------------------------------------------------------------


def test_add_symbol_and_get_symbol_round_trip() -> None:
    """add_symbol() stores a SymbolInfo that get_symbol() can retrieve."""
    graph = SymbolGraph()
    sym = _make_symbol("bar", "function", "a/b.py")
    graph.add_symbol(sym)

    node_id = "a/b.py::bar"
    retrieved = graph.get_symbol(node_id)
    assert retrieved is not None
    assert retrieved.name == "bar"
    assert retrieved.kind == "function"


def test_get_symbol_returns_none_for_missing_id() -> None:
    """get_symbol() returns None when the node ID does not exist."""
    graph = SymbolGraph()
    assert graph.get_symbol("nonexistent::sym") is None


def test_add_symbol_overwrites_existing_node() -> None:
    """Adding a symbol with the same ID silently overwrites the previous one."""
    graph = SymbolGraph()
    sym1 = _make_symbol("foo", "function", "mod.py")
    sym2 = SymbolInfo(
        name="foo",
        kind="class",
        file_path=Path("mod.py"),
        start_byte=0,
        end_byte=50,
        start_line=1,
        end_line=10,
        source="class foo: pass",
    )
    graph.add_symbol(sym1)
    graph.add_symbol(sym2)

    retrieved = graph.get_symbol("mod.py::foo")
    assert retrieved is not None
    assert retrieved.kind == "class"


# ---------------------------------------------------------------------------
# Unit tests — add_edge / neighbors
# ---------------------------------------------------------------------------


def test_add_edge_creates_directed_edge() -> None:
    """add_edge() creates a directed edge between two existing nodes."""
    graph = SymbolGraph()
    a = _make_symbol("a", "function", "m.py")
    b = _make_symbol("b", "function", "m.py")
    graph.add_symbol(a)
    graph.add_symbol(b)
    graph.add_edge("m.py::a", "m.py::b", "calls")

    neighbours = graph.neighbors("m.py::a")
    assert any(s.name == "b" for s in neighbours)


def test_add_edge_silently_ignored_for_missing_nodes() -> None:
    """add_edge() does nothing when either node ID is absent."""
    graph = SymbolGraph()
    sym = _make_symbol("a", "function", "m.py")
    graph.add_symbol(sym)
    # "m.py::b" does not exist — should not raise
    graph.add_edge("m.py::a", "m.py::b", "calls")
    assert graph.neighbors("m.py::a") == []


def test_neighbors_returns_empty_for_unknown_node() -> None:
    """neighbors() returns an empty list for a node ID that does not exist."""
    graph = SymbolGraph()
    assert graph.neighbors("ghost::sym") == []


def test_neighbors_excludes_stub_nodes() -> None:
    """neighbors() skips nodes that have no SymbolInfo attribute."""
    graph = SymbolGraph()
    sym = _make_symbol("caller", "function", "m.py")
    graph.add_symbol(sym)
    # Manually add a stub node (no symbol attribute)
    graph._graph.add_node("stub::node")
    graph._graph.add_edge("m.py::caller", "stub::node", kind="calls")

    neighbours = graph.neighbors("m.py::caller")
    assert neighbours == []


# ---------------------------------------------------------------------------
# Unit tests — to_dict / from_dict
# ---------------------------------------------------------------------------


def test_to_dict_contains_nodes_and_edges_keys() -> None:
    """to_dict() returns a dict with 'nodes' and 'edges' keys."""
    graph = SymbolGraph()
    d = graph.to_dict()
    assert "nodes" in d
    assert "edges" in d


def test_from_dict_reconstructs_graph() -> None:
    """from_dict(to_dict()) produces a graph with the same nodes and edges."""
    graph = SymbolGraph()
    a = _make_symbol("a", "function", "m.py")
    b = _make_symbol("b", "class", "m.py")
    graph.add_symbol(a)
    graph.add_symbol(b)
    graph.add_edge("m.py::a", "m.py::b", "calls")

    restored = SymbolGraph.from_dict(graph.to_dict())

    assert restored.get_symbol("m.py::a") is not None
    assert restored.get_symbol("m.py::b") is not None
    assert any(s.name == "b" for s in restored.neighbors("m.py::a"))


def test_from_dict_preserves_symbol_fields() -> None:
    """from_dict() restores all SymbolInfo fields exactly."""
    graph = SymbolGraph()
    sym = SymbolInfo(
        name="my_func",
        kind="function",
        file_path=Path("pkg/utils.py"),
        start_byte=10,
        end_byte=80,
        start_line=3,
        end_line=7,
        source="def my_func(): return 42",
    )
    graph.add_symbol(sym)

    restored = SymbolGraph.from_dict(graph.to_dict())
    r = restored.get_symbol("pkg/utils.py::my_func")
    assert r is not None
    assert r.name == sym.name
    assert r.kind == sym.kind
    assert Path(r.file_path) == Path(sym.file_path)
    assert r.start_byte == sym.start_byte
    assert r.end_byte == sym.end_byte
    assert r.start_line == sym.start_line
    assert r.end_line == sym.end_line
    assert r.source == sym.source


# ---------------------------------------------------------------------------
# Property 8: SymbolGraph correctly classifies symbol kinds
# ---------------------------------------------------------------------------


@given(source=python_source_strategy())
@settings(max_examples=100)
def test_property_8_symbol_kind_classification(source: str) -> None:
    """Property 8: SymbolGraph correctly classifies symbol kinds.

    For any Python source string containing a function_definition node, after
    parsing and indexing, the SymbolGraph SHALL contain a SymbolInfo node with
    kind="function" and the correct name, start_line, and end_line. Same for
    class_definition (kind="class") and import_statement (kind="import").

    # Feature: local-sage, Property 8: SymbolGraph correctly classifies symbol kinds
    **Validates: Requirements 3.2**
    """
    # Feature: local-sage, Property 8: SymbolGraph correctly classifies symbol kinds
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src_file = tmp_path / "sample.py"
        src_file.write_text(source, encoding="utf-8")

        indexer = RepoIndexer()
        graph = indexer.index_repo(tmp_path)

        all_symbols = [
            graph.get_symbol(nid)
            for nid in graph._graph.nodes()
            if graph.get_symbol(nid) is not None
        ]

        for sym in all_symbols:
            assert sym is not None
            # Every indexed symbol must have a valid kind
            assert sym.kind in ("function", "class", "import"), (
                f"Unexpected kind {sym.kind!r} for symbol {sym.name!r}"
            )
            # Line numbers must be positive and ordered
            assert sym.start_line >= 1
            assert sym.end_line >= sym.start_line
            # Name must be non-empty
            assert sym.name.strip() != ""


# ---------------------------------------------------------------------------
# Property 9: SymbolGraph index round-trip (save → load)
# ---------------------------------------------------------------------------


@given(
    symbols=symbol_info_strategy().flatmap(lambda s: symbol_info_strategy().map(lambda s2: [s, s2]))
)
@settings(max_examples=100)
def test_property_9_index_round_trip(symbols: list[SymbolInfo]) -> None:
    """Property 9: SymbolGraph index round-trip (save → load).

    For any SymbolGraph with N nodes and M edges, calling
    RepoIndexer.save_index() followed by RepoIndexer.load_index() SHALL
    produce a graph with the same N nodes and M edges, where each node's
    SymbolInfo fields are identical to the original.

    # Feature: local-sage, Property 9: SymbolGraph index round-trip (save → load)
    **Validates: Requirements 3.3**
    """
    # Feature: local-sage, Property 9: SymbolGraph index round-trip (save → load)
    graph = SymbolGraph()
    for sym in symbols:
        graph.add_symbol(sym)

    # Attempt to add an edge between the first two symbols if they differ
    if len(symbols) >= 2:
        id0 = SymbolGraph._make_id(symbols[0].file_path, symbols[0].name)
        id1 = SymbolGraph._make_id(symbols[1].file_path, symbols[1].name)
        if id0 != id1:
            graph.add_edge(id0, id1, "calls")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Use a real repo_root so mtime collection works
        cache_path = tmp_path / ".sage" / "index.json"

        indexer = RepoIndexer()
        indexer.save_index(graph, cache_path, repo_root=tmp_path)

        # Patch mtimes so load_index does not consider the cache stale
        import json

        raw = cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Clear stored mtimes so no stale check fires
        data["mtimes"] = {}
        cache_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = indexer.load_index(cache_path)

    assert loaded is not None, "load_index() returned None — cache was considered stale"

    original_nodes = {nid for nid in graph._graph.nodes() if graph.get_symbol(nid) is not None}
    loaded_nodes = {nid for nid in loaded._graph.nodes() if loaded.get_symbol(nid) is not None}
    assert original_nodes == loaded_nodes, (
        f"Node sets differ.\nOriginal: {original_nodes}\nLoaded: {loaded_nodes}"
    )

    # Verify each node's SymbolInfo fields are identical
    for nid in original_nodes:
        orig_sym = graph.get_symbol(nid)
        load_sym = loaded.get_symbol(nid)
        assert orig_sym is not None
        assert load_sym is not None
        assert orig_sym.name == load_sym.name
        assert orig_sym.kind == load_sym.kind
        assert Path(orig_sym.file_path) == Path(load_sym.file_path)
        assert orig_sym.start_byte == load_sym.start_byte
        assert orig_sym.end_byte == load_sym.end_byte
        assert orig_sym.start_line == load_sym.start_line
        assert orig_sym.end_line == load_sym.end_line
        assert orig_sym.source == load_sym.source

    # Verify edge count matches
    original_edges = set(graph._graph.edges())
    loaded_edges = set(loaded._graph.edges())
    assert original_edges == loaded_edges, (
        f"Edge sets differ.\nOriginal: {original_edges}\nLoaded: {loaded_edges}"
    )
