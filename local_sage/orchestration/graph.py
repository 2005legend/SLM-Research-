"""LangGraph StateGraph definition for Layer 2 — Orchestration.

Builds and compiles the agent's execution graph:

    planner → context_retriever → code_generator → validator
                                                        │
                                    ┌───────────────────┤
                                    │ passed=True        │ passed=False, retry < max
                                    ▼                    ▼
                              apply_patch          code_generator (retry)
                                    │
                                    ▼
                              memory_writer
                                    │
                                    ▼
                                   END

The conditional edge ``route_after_validation`` decides whether to retry
code generation, proceed to apply+memory writing, or terminate with failure.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from local_sage.orchestration.nodes import (
    apply_patch_node,
    code_generator_node,
    context_retriever_node,
    memory_writer_node,
    planner_node,
    validator_node,
)
from local_sage.orchestration.state import AgentState

logger = logging.getLogger(__name__)

# Type alias for the routing decision
_RouteDecision = Literal["code_generator", "apply_patch", "__end__"]


def route_after_validation(state: AgentState) -> _RouteDecision:
    """Decide the next node after the validator runs.

    Routing rules:
    - ``passed=True``  → ``"apply_patch"``
    - ``passed=False`` and ``retry_count < max_retries`` → ``"code_generator"``
    - ``passed=False`` and ``retry_count >= max_retries`` → END

    Args:
        state: Current agent state after the validator node has run.

    Returns:
        The name of the next node to execute, or ``END``.
    """
    result = state.validation_result
    if result is not None and result.passed:
        return "apply_patch"
    if state.retry_count < state.max_retries:
        logger.info(
            "Validation failed (retry %d/%d); re-entering code_generator.",
            state.retry_count,
            state.max_retries,
        )
        return "code_generator"
    logger.warning(
        "Max retries (%d) reached without a passing patch; terminating.",
        state.max_retries,
    )
    return END  # type: ignore[return-value]


def build_graph() -> object:
    """Build and compile the local-sage LangGraph StateGraph.

    Registers all nodes and wires the edges according to the design.

    Returns:
        A compiled ``CompiledGraph`` ready to be invoked with an
        ``AgentState`` dict.
    """
    graph: StateGraph = StateGraph(AgentState)
    _register_nodes(graph)
    _wire_edges(graph)
    return graph.compile()


def _register_nodes(graph: StateGraph) -> None:
    """Add all agent nodes to *graph*.

    Args:
        graph: The StateGraph to add nodes to.
    """
    graph.add_node("planner", planner_node)
    graph.add_node("context_retriever", context_retriever_node)
    graph.add_node("code_generator", code_generator_node)
    graph.add_node("validator", validator_node)
    graph.add_node("apply_patch", apply_patch_node)
    graph.add_node("memory_writer", memory_writer_node)


def _wire_edges(graph: StateGraph) -> None:
    """Wire all edges and the conditional routing into *graph*.

    Args:
        graph: The StateGraph to wire edges into.
    """
    graph.set_entry_point("planner")
    graph.add_edge("planner", "context_retriever")
    graph.add_edge("context_retriever", "code_generator")
    graph.add_edge("code_generator", "validator")
    graph.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "code_generator": "code_generator",
            "apply_patch": "apply_patch",
            END: END,
        },
    )
    graph.add_edge("apply_patch", "memory_writer")
    graph.add_edge("memory_writer", END)
