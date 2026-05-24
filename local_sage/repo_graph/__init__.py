"""Layer 3 — Repo Graph: tree-sitter parser, symbol index, and call/import graphs.

Public API:
    SymbolInfo       — dataclass describing a single indexed symbol.
    SymbolGraph      — NetworkX-backed graph of symbols and their relationships.
    RepoIndexer      — walks a Python repo and populates a SymbolGraph.
    ContextSelector  — selects the top-K most relevant symbols for a task.
    ImpactAnalyzer   — determines which symbols are affected by a patch.
    ImpactReport     — dataclass returned by ImpactAnalyzer.analyze().
    RepoGraphError   — base exception for all repo-graph errors.
    IndexLoadError   — raised when the cached index cannot be loaded.
    ParseError       — raised when a source file cannot be parsed.
"""

from local_sage.repo_graph.exceptions import IndexLoadError, ParseError, RepoGraphError
from local_sage.repo_graph.graph import SymbolGraph, SymbolInfo
from local_sage.repo_graph.impact import ImpactAnalyzer, ImpactReport

__all__ = [
    "SymbolInfo",
    "SymbolGraph",
    "RepoIndexer",
    "ContextSelector",
    "ImpactAnalyzer",
    "ImpactReport",
    "RepoGraphError",
    "IndexLoadError",
    "ParseError",
]
