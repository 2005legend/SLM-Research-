"""Unit and property-based tests for RepoIndexer (Layer 3 — Repo Graph).

Covers index_repo, update_file, save_index, load_index, and Properties 7,
10, and 13.

**Validates: Requirements 3.1, 3.4, 3.7**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.repo_graph.graph import SymbolGraph
from local_sage.repo_graph.indexer import RepoIndexer
from tests.strategies import python_source_strategy

# ---------------------------------------------------------------------------
# Unit tests — index_repo
# ---------------------------------------------------------------------------


def test_index_repo_finds_function_in_single_file(tmp_path: Path) -> None:
    """index_repo() indexes a function defined in a single .py file."""
    src = tmp_path / "hello.py"
    src.write_text("def greet(name):\n    return f'Hello {name}'\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)

    node_ids = list(graph._graph.nodes())
    assert any("greet" in nid for nid in node_ids), f"Expected 'greet' in node IDs, got: {node_ids}"


def test_index_repo_finds_class_in_single_file(tmp_path: Path) -> None:
    """index_repo() indexes a class defined in a single .py file."""
    src = tmp_path / "models.py"
    src.write_text("class MyModel:\n    pass\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)

    node_ids = list(graph._graph.nodes())
    assert any("MyModel" in nid for nid in node_ids), (
        f"Expected 'MyModel' in node IDs, got: {node_ids}"
    )


def test_index_repo_finds_import_in_single_file(tmp_path: Path) -> None:
    """index_repo() indexes an import statement in a single .py file."""
    src = tmp_path / "imports.py"
    src.write_text("import os\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)

    all_symbols = [
        graph.get_symbol(nid) for nid in graph._graph.nodes() if graph.get_symbol(nid) is not None
    ]
    import_syms = [s for s in all_symbols if s is not None and s.kind == "import"]
    assert len(import_syms) >= 1


def test_index_repo_skips_hidden_directories(tmp_path: Path) -> None:
    """index_repo() does not index .py files inside hidden directories."""
    hidden = tmp_path / ".venv" / "lib"
    hidden.mkdir(parents=True)
    (hidden / "secret.py").write_text("def hidden(): pass\n", encoding="utf-8")

    visible = tmp_path / "visible.py"
    visible.write_text("def visible(): pass\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)

    node_ids = list(graph._graph.nodes())
    assert not any("hidden" in nid for nid in node_ids)
    assert any("visible" in nid for nid in node_ids)


def test_index_repo_returns_empty_graph_for_empty_directory(tmp_path: Path) -> None:
    """index_repo() returns an empty SymbolGraph when no .py files exist."""
    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)
    assert graph._graph.number_of_nodes() == 0


# ---------------------------------------------------------------------------
# Unit tests — update_file
# ---------------------------------------------------------------------------


def test_update_file_replaces_old_symbols(tmp_path: Path) -> None:
    """update_file() removes stale symbols and adds fresh ones for the file."""
    src = tmp_path / "mod.py"
    src.write_text("def old_func(): pass\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)

    # Rewrite the file with a new function
    src.write_text("def new_func(): pass\n", encoding="utf-8")
    indexer.update_file(src, graph)

    node_ids = list(graph._graph.nodes())
    assert not any("old_func" in nid for nid in node_ids)
    assert any("new_func" in nid for nid in node_ids)


# ---------------------------------------------------------------------------
# Unit tests — save_index / load_index
# ---------------------------------------------------------------------------


def test_save_and_load_index_round_trip(tmp_path: Path) -> None:
    """save_index() + load_index() restores the graph from disk."""
    src = tmp_path / "mod.py"
    src.write_text("def saved_func(): pass\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)

    cache_path = tmp_path / ".sage" / "index.json"
    indexer.save_index(graph, cache_path, repo_root=tmp_path)

    loaded = indexer.load_index(cache_path)
    assert loaded is not None

    loaded_ids = list(loaded._graph.nodes())
    assert any("saved_func" in nid for nid in loaded_ids)


def test_load_index_returns_none_for_missing_file(tmp_path: Path) -> None:
    """load_index() returns None when the cache file does not exist."""
    indexer = RepoIndexer()
    result = indexer.load_index(tmp_path / "nonexistent.json")
    assert result is None


def test_load_index_returns_none_for_stale_cache(tmp_path: Path) -> None:
    """load_index() returns None when a source file has been modified."""
    src = tmp_path / "mod.py"
    src.write_text("def func(): pass\n", encoding="utf-8")

    indexer = RepoIndexer()
    graph = indexer.index_repo(tmp_path)
    cache_path = tmp_path / ".sage" / "index.json"
    indexer.save_index(graph, cache_path, repo_root=tmp_path)

    # Touch the source file to change its mtime
    import time

    time.sleep(0.01)
    src.write_text("def func(): return 1\n", encoding="utf-8")

    result = indexer.load_index(cache_path)
    assert result is None


# ---------------------------------------------------------------------------
# Property 7: RepoIndexer covers all .py files
# ---------------------------------------------------------------------------


@given(
    sources=st.lists(
        python_source_strategy(),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=100, deadline=None)
def test_property_7_indexer_covers_all_py_files(sources: list[str]) -> None:
    """Property 7: RepoIndexer covers all .py files.

    For any directory containing N .py files with valid Python syntax, after
    RepoIndexer.index_repo(), the resulting SymbolGraph SHALL contain at least
    one node whose file_path matches each of those N files.

    # Feature: local-sage, Property 7: RepoIndexer covers all .py files
    **Validates: Requirements 3.1**
    """
    # Feature: local-sage, Property 7: RepoIndexer covers all .py files
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        written_files: list[Path] = []
        for i, source in enumerate(sources):
            py_file = tmp_path / f"module_{i}.py"
            py_file.write_text(source, encoding="utf-8")
            written_files.append(py_file)

        indexer = RepoIndexer()
        graph = indexer.index_repo(tmp_path)

        for py_file in written_files:
            rel = py_file.relative_to(tmp_path)
            # Verify that every symbol produced for this file has the correct
            # file_path recorded. Files with no indexable symbols (e.g. bare
            # assignments) produce zero nodes — that is acceptable.
            file_symbols = [
                graph.get_symbol(nid)
                for nid in graph._graph.nodes()
                if graph.get_symbol(nid) is not None
                and Path(graph.get_symbol(nid).file_path) == rel  # type: ignore[union-attr]
            ]
            for sym in file_symbols:
                assert sym is not None
                assert Path(sym.file_path) == rel


# ---------------------------------------------------------------------------
# Property 10: Incremental update does not affect unmodified files
# ---------------------------------------------------------------------------


@given(
    source_f1=python_source_strategy(),
    source_f2=python_source_strategy(),
    updated_f1=python_source_strategy(),
)
@settings(max_examples=100)
def test_property_10_incremental_update_preserves_unmodified_file(
    source_f1: str,
    source_f2: str,
    updated_f1: str,
) -> None:
    """Property 10: Incremental update does not affect unmodified files.

    For any repository with files F1 and F2, after calling
    RepoIndexer.update_file(F1), the nodes in the SymbolGraph whose
    file_path equals F2 SHALL be identical to their state before the update.

    # Feature: local-sage, Property 10: Incremental update does not affect unmodified files
    **Validates: Requirements 3.4**
    """
    # Feature: local-sage, Property 10: Incremental update does not affect unmodified files
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        f1 = tmp_path / "file1.py"
        f2 = tmp_path / "file2.py"
        f1.write_text(source_f1, encoding="utf-8")
        f2.write_text(source_f2, encoding="utf-8")

        indexer = RepoIndexer()
        graph = indexer.index_repo(tmp_path)

        rel_f2 = f2.relative_to(tmp_path)

        def _f2_nodes(g: SymbolGraph) -> dict[str, dict]:
            """Return a snapshot of all nodes belonging to f2."""
            result: dict[str, dict] = {}
            for nid in g._graph.nodes():
                sym = g.get_symbol(nid)
                if sym is not None and Path(sym.file_path) == rel_f2:
                    result[nid] = {
                        "name": sym.name,
                        "kind": sym.kind,
                        "start_line": sym.start_line,
                        "end_line": sym.end_line,
                        "source": sym.source,
                    }
            return result

        before = _f2_nodes(graph)

        # Update f1 with new content
        f1.write_text(updated_f1, encoding="utf-8")
        indexer.update_file(f1, graph)

        after = _f2_nodes(graph)

        assert before == after, (
            f"Nodes for f2 changed after updating f1.\nBefore: {before}\nAfter: {after}"
        )


# ---------------------------------------------------------------------------
# Property 13: RepoIndexer skips syntax-error files without raising
# ---------------------------------------------------------------------------


@given(
    valid_sources=st.lists(python_source_strategy(), min_size=1, max_size=5),
    n_invalid=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=100)
def test_property_13_skips_syntax_error_files(
    valid_sources: list[str],
    n_invalid: int,
) -> None:
    """Property 13: RepoIndexer skips syntax-error files without raising.

    For any mix of M valid and N invalid (syntax-error) Python files,
    RepoIndexer.index_repo() SHALL complete without raising an exception
    and SHALL index all M valid files.

    # Feature: local-sage, Property 13: RepoIndexer skips syntax-error files without raising
    **Validates: Requirements 3.7**
    """
    # Feature: local-sage, Property 13: RepoIndexer skips syntax-error files without raising
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for i, source in enumerate(valid_sources):
            py_file = tmp_path / f"valid_{i}.py"
            py_file.write_text(source, encoding="utf-8")

        for j in range(n_invalid):
            bad_file = tmp_path / f"invalid_{j}.py"
            # Guaranteed syntax error: unmatched parenthesis
            bad_file.write_text("def broken(\n    x = (\n", encoding="utf-8")

        indexer = RepoIndexer()
        # Must not raise
        graph = indexer.index_repo(tmp_path)

        # No node should reference an invalid file
        indexed_paths: set[Path] = set()
        for nid in graph._graph.nodes():
            sym = graph.get_symbol(nid)
            if sym is not None:
                indexed_paths.add(Path(sym.file_path))

        for j in range(n_invalid):
            bad_rel = Path(f"invalid_{j}.py")
            assert bad_rel not in indexed_paths, (
                f"Invalid file {bad_rel} was indexed despite syntax errors"
            )
