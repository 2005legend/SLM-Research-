"""ContextSelector for Layer 3 — Repo Graph.

Selects the most relevant symbols for a given task using Personalized PageRank
on the SymbolGraph, with an optional recency boost for recently modified symbols.
"""

from __future__ import annotations

import re

import networkx as nx

from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo


class ContextSelector:
    """Selects the top-K most relevant symbols for a coding task.

    Uses Personalized PageRank on the SymbolGraph to rank symbols by their
    structural relevance to the task description.  Symbols whose names contain
    task tokens are seeded with higher personalization weights, and PageRank
    propagates that relevance through call and import edges.

    An optional recency boost multiplies the scores of recently modified
    symbols before the final top-K cut.

    Example::

        selector = ContextSelector()
        symbols = selector.select("add rate limiter", graph, top_k=5)
    """

    def __init__(self, recency_factor: float = 1.5) -> None:
        """Initialise the selector.

        Args:
            recency_factor: Score multiplier applied to recently modified
                symbols.  Must be >= 1.0.  Defaults to ``1.5``.
        """
        self._recency_factor = recency_factor

    def select(
        self,
        task: str,
        graph: SymbolGraph,
        top_k: int = 10,
        recent_symbol_ids: set[str] | None = None,
    ) -> list[SymbolInfo]:
        """Return the top-K symbols most relevant to *task*.

        Args:
            task: Natural-language task description used to seed the
                personalization vector.
            graph: The ``SymbolGraph`` to rank.
            top_k: Maximum number of symbols to return.
            recent_symbol_ids: Optional set of symbol IDs that were modified
                in the current session.  Their scores are multiplied by
                ``recency_factor`` before ranking.

        Returns:
            A list of at most *top_k* ``SymbolInfo`` objects ordered by
            descending relevance score.  Nodes without a ``SymbolInfo``
            attribute are skipped.
        """
        if graph._graph.number_of_nodes() == 0:
            return []

        personalization = self._compute_personalization(task, graph)
        scores: dict[str, float] = nx.pagerank(
            graph._graph,
            personalization=personalization,
            alpha=0.85,
        )

        scores = self._apply_recency_boost(scores, recent_symbol_ids)

        return self._top_k_symbols(scores, graph, top_k)

    def _compute_personalization(
        self,
        task: str,
        graph: SymbolGraph,
    ) -> dict[str, float]:
        """Build a normalized personalization vector from *task* tokens.

        Each symbol whose name contains at least one task token (case-
        insensitive) receives weight ``1.0``; all others receive ``0.0``.
        If no symbols match, all symbols receive equal weight so that
        ``nx.pagerank`` does not raise a ``ZeroDivisionError``.

        The resulting weights are normalized to sum to ``1.0``.

        Args:
            task: Natural-language task description.
            graph: The ``SymbolGraph`` whose nodes are scored.

        Returns:
            A dictionary mapping every node ID to its normalized weight.
        """
        tokens = _tokenize(task)
        node_ids = list(graph._graph.nodes())

        weights: dict[str, float] = {}
        for node_id in node_ids:
            symbol = graph.get_symbol(node_id)
            name = symbol.name if symbol is not None else node_id
            weights[node_id] = 1.0 if _name_matches(name, tokens) else 0.0

        if all(w == 0.0 for w in weights.values()):
            weights = {nid: 1.0 for nid in node_ids}

        return _normalize(weights)

    def _apply_recency_boost(
        self,
        scores: dict[str, float],
        recent_symbol_ids: set[str] | None,
    ) -> dict[str, float]:
        """Multiply scores for recently modified symbols by *recency_factor*.

        Args:
            scores: Raw PageRank scores keyed by node ID.
            recent_symbol_ids: Symbol IDs to boost, or ``None`` to skip.

        Returns:
            A new scores dictionary with the recency boost applied.
        """
        if not recent_symbol_ids:
            return scores
        return {
            nid: (score * self._recency_factor if nid in recent_symbol_ids else score)
            for nid, score in scores.items()
        }

    def _top_k_symbols(
        self,
        scores: dict[str, float],
        graph: SymbolGraph,
        top_k: int,
    ) -> list[SymbolInfo]:
        """Sort *scores* descending and return the top-K ``SymbolInfo`` objects.

        Nodes that have no ``SymbolInfo`` attribute are skipped and do not
        count toward *top_k*.

        Args:
            scores: Final scores keyed by node ID.
            graph: Source of ``SymbolInfo`` objects.
            top_k: Maximum number of results to return.

        Returns:
            A list of at most *top_k* ``SymbolInfo`` objects.
        """
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        result: list[SymbolInfo] = []
        for node_id, _ in ranked:
            if len(result) >= top_k:
                break
            symbol = graph.get_symbol(node_id)
            if symbol is not None:
                result.append(symbol)
        return result


# ---------------------------------------------------------------------------
# Module-level helpers (private)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Split *text* on whitespace and punctuation, returning lowercase tokens.

    Args:
        text: Arbitrary string to tokenize.

    Returns:
        A list of non-empty lowercase tokens.
    """
    return [t.lower() for t in re.split(r"[\s\W]+", text) if t]


def _name_matches(name: str, tokens: list[str]) -> bool:
    """Return ``True`` if any token appears in *name* (case-insensitive).

    Args:
        name: Symbol name to test.
        tokens: Lowercase tokens derived from the task string.

    Returns:
        ``True`` if at least one token is a substring of the lowercased name.
    """
    lower_name = name.lower()
    return any(token in lower_name for token in tokens)


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """Normalize *weights* so they sum to ``1.0``.

    Args:
        weights: Raw weight mapping.  Must not be empty.

    Returns:
        A new dictionary with the same keys and normalized values.
    """
    total = sum(weights.values())
    if total == 0.0:
        n = len(weights)
        return {k: 1.0 / n for k in weights}
    return {k: v / total for k, v in weights.items()}
