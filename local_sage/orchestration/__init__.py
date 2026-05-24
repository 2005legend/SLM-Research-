"""Layer 2 — Orchestration: LangGraph-based agent loop.

Public API:
    AgentState  — typed state dataclass shared across all LangGraph nodes.
    build_graph — factory function that compiles and returns the StateGraph.
"""

from local_sage.orchestration.state import AgentState

__all__ = [
    "AgentState",
    "build_graph",
]
