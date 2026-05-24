"""AgentState dataclass shared across all LangGraph nodes.

This is the single typed state object passed between every node in the
LangGraph StateGraph.  Each node receives the full state and returns a
``dict`` containing only the fields it modifies; LangGraph merges the
returned dict back into the state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from local_sage.repo_graph.graph import SymbolInfo
from local_sage.validation.result import ValidationResult
from local_sage.wiki.manager import WikiEntry


@dataclass
class AgentState:
    """Typed state object passed between all nodes in the LangGraph StateGraph.

    Every node receives the full state and returns a dict containing only the
    fields it modifies. LangGraph merges the returned dict back into the state.

    Attributes:
        task: Natural-language description of the coding task submitted by
            the user.
        plan: Ordered list of sub-task descriptions produced by the planner
            node.
        context_symbols: Top-K relevant symbols selected by the
            ContextSelector for the current task.
        wiki_context: Relevant wiki entries retrieved by the WikiManager for
            the current task.
        patch: Unified diff string produced by the code generator, or
            ``None`` if no patch has been generated yet.
        validation_result: Result of the most recent ValidationRunner run,
            or ``None`` if validation has not yet been attempted.
        retry_count: Number of code-generation retries attempted so far in
            the current task loop.
        max_retries: Maximum allowed retries before the agent reports failure
            and exits without applying a patch.
        session_id: Identifier of the current agent session (from
            SessionManager).
        error: Human-readable error message if the agent encountered a fatal
            error, or ``None`` if no error has occurred.
    """

    task: str = ""
    plan: list[str] = field(default_factory=list)
    context_symbols: list[SymbolInfo] = field(default_factory=list)
    wiki_context: list[WikiEntry] = field(default_factory=list)
    patch: str | None = None
    validation_result: ValidationResult | None = None
    retry_count: int = 0
    max_retries: int = 3
    session_id: str = ""
    error: str | None = None
