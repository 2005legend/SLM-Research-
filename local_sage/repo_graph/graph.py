"""SymbolGraph and SymbolInfo for Layer 3 — Repo Graph.

Provides the core data structures for the repository symbol index:
- ``SymbolInfo``: metadata for a single indexed symbol.
- ``SymbolGraph``: a NetworkX DiGraph of symbols and their relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import networkx as nx


@dataclass
class SymbolInfo:
    """Metadata for a single indexed symbol in the repository.

    Attributes:
        name: The symbol's unqualified name (e.g. ``"OllamaClient"``).
        kind: One of ``"function"``, ``"class"``, or ``"import"``.
        file_path: Absolute or repo-relative path to the source file.
        start_byte: Byte offset of the symbol's first character.
        end_byte: Byte offset one past the symbol's last character.
        start_line: 1-based line number of the symbol's first line.
        end_line: 1-based line number of the symbol's last line.
        source: Full source text of the symbol.
    """

    name: str
    kind: Literal["function", "class", "import"]
    file_path: Path
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    source: str


class SymbolGraph:
    """NetworkX-backed directed graph of repository symbols.

    Nodes are symbol IDs of the form ``"<relative_file_path>::<symbol_name>"``,
    e.g. ``"local_sage/model/client.py::OllamaClient"``.  Each node stores its
    ``SymbolInfo`` as a node attribute.  Edges carry a ``kind`` attribute that
    is either ``"calls"`` or ``"imports"``.

    Example::

        graph = SymbolGraph()
        info = SymbolInfo(
            name="foo",
            kind="function",
            file_path=Path("pkg/mod.py"),
            start_byte=0,
            end_byte=10,
            start_line=1,
            end_line=3,
            source="def foo(): ...",
        )
        graph.add_symbol(info)
        symbol_id = "pkg/mod.py::foo"
        retrieved = graph.get_symbol(symbol_id)
    """

    def __init__(self) -> None:
        """Initialise an empty SymbolGraph."""
        self._graph: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_symbol(self, symbol: SymbolInfo) -> None:
        """Add a symbol to the graph as a node.

        The node ID is derived from ``symbol.file_path`` and ``symbol.name``
        using the convention ``"<file_path>::<name>"``.  If a node with the
        same ID already exists it is silently overwritten.

        Args:
            symbol: The ``SymbolInfo`` to add.
        """
        node_id = self._make_id(symbol.file_path, symbol.name)
        self._graph.add_node(node_id, symbol=symbol)

    def add_edge(self, from_id: str, to_id: str, kind: str) -> None:
        """Add a directed edge between two symbol IDs.

        Both node IDs must already exist in the graph.  If either is absent
        the call is silently ignored — no stub nodes are created.

        Args:
            from_id: Source symbol ID.
            to_id: Target symbol ID.
            kind: Relationship kind, typically ``"calls"`` or ``"imports"``.
        """
        if from_id not in self._graph or to_id not in self._graph:
            return
        self._graph.add_edge(from_id, to_id, kind=kind)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_symbol(self, symbol_id: str) -> SymbolInfo | None:
        """Return the ``SymbolInfo`` for *symbol_id*, or ``None`` if absent.

        Args:
            symbol_id: Node ID in the form ``"<file_path>::<name>"``.

        Returns:
            The associated ``SymbolInfo``, or ``None`` if the node does not
            exist or has no ``symbol`` attribute.
        """
        if symbol_id not in self._graph:
            return None
        result: SymbolInfo | None = self._graph.nodes[symbol_id].get("symbol")
        return result

    def neighbors(self, symbol_id: str) -> list[SymbolInfo]:
        """Return ``SymbolInfo`` objects for all direct successors of *symbol_id*.

        Only neighbours that have a ``symbol`` attribute are included; stub
        nodes created implicitly by ``add_edge`` are skipped.

        Args:
            symbol_id: Node ID whose successors are requested.

        Returns:
            A list of ``SymbolInfo`` objects for each successor node.
        """
        if symbol_id not in self._graph:
            return []
        result: list[SymbolInfo] = []
        for neighbour_id in self._graph.successors(symbol_id):
            info = self._graph.nodes[neighbour_id].get("symbol")
            if info is not None:
                result.append(info)
        return result

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the graph to a plain dictionary for JSON serialisation.

        Returns:
            Dict with ``"nodes"`` and ``"edges"`` lists.
        """
        nodes = [
            self._node_to_dict(nid, attrs)
            for nid, attrs in self._graph.nodes(data=True)
            if attrs.get("symbol")
        ]
        edges: list[dict[str, Any]] = [
            {"from": u, "to": v, "kind": data.get("kind", "")}
            for u, v, data in self._graph.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def _node_to_dict(self, node_id: str, attrs: dict[str, Any]) -> dict[str, Any]:
        """Serialise a single node to a dict.

        Args:
            node_id: The node's string ID.
            attrs: Node attribute dict containing ``"symbol"``.

        Returns:
            A ``{"id": str, "symbol": dict}`` entry.
        """
        symbol: SymbolInfo = attrs["symbol"]
        return {
            "id": node_id,
            "symbol": {
                "name": symbol.name,
                "kind": symbol.kind,
                "file_path": Path(symbol.file_path).as_posix(),
                "start_byte": symbol.start_byte,
                "end_byte": symbol.end_byte,
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "source": symbol.source,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SymbolGraph:
        """Reconstruct a ``SymbolGraph`` from a serialised dictionary.

        This is the inverse of :meth:`to_dict`.  ``file_path`` values are
        restored as ``pathlib.Path`` objects.

        Args:
            data: A dictionary previously produced by :meth:`to_dict`.

        Returns:
            A fully populated ``SymbolGraph`` instance.
        """
        graph = cls()

        for node_entry in data.get("nodes", []):
            sym_data: dict[str, Any] = node_entry["symbol"]
            symbol = SymbolInfo(
                name=sym_data["name"],
                kind=sym_data["kind"],
                file_path=Path(sym_data["file_path"]),
                start_byte=sym_data["start_byte"],
                end_byte=sym_data["end_byte"],
                start_line=sym_data["start_line"],
                end_line=sym_data["end_line"],
                source=sym_data["source"],
            )
            graph.add_symbol(symbol)

        for edge_entry in data.get("edges", []):
            graph.add_edge(edge_entry["from"], edge_entry["to"], edge_entry["kind"])

        return graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(file_path: Path | str, name: str) -> str:
        """Build a canonical node ID from a file path and symbol name.

        Args:
            file_path: Path to the source file (converted to POSIX string).
            name: Unqualified symbol name.

        Returns:
            A string of the form ``"<posix_path>::<name>"``.
        """
        return f"{Path(file_path).as_posix()}::{name}"
