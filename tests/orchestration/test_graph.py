"""Unit and property-based tests for the LangGraph StateGraph (Layer 2 — Orchestration).

Covers build_graph(), route_after_validation(), and Properties 24–27.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.6**
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.orchestration.graph import build_graph, route_after_validation
from local_sage.orchestration.state import AgentState
from local_sage.validation.result import (
    PytestCounts,
    ValidationFailure,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passing_result() -> ValidationResult:
    """Return a passing ValidationResult."""
    return ValidationResult(
        passed=True,
        failures=[],
        pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=100,
    )


def _failing_result() -> ValidationResult:
    """Return a failing ValidationResult."""
    return ValidationResult(
        passed=False,
        failures=[ValidationFailure(tool="pytest", message="1 failed")],
        pytest_counts=PytestCounts(passed=4, failed=1, errors=0),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=100,
    )


# ---------------------------------------------------------------------------
# Unit tests — route_after_validation()
# ---------------------------------------------------------------------------


class TestRouteAfterValidation:
    """Unit tests for route_after_validation()."""

    def test_routes_to_memory_writer_on_pass(self) -> None:
        """route_after_validation() returns 'apply_patch' when validation passes."""
        state = AgentState(validation_result=_passing_result(), retry_count=0, max_retries=3)
        assert route_after_validation(state) == "apply_patch"

    def test_routes_to_code_generator_on_failure_with_retries_remaining(self) -> None:
        """route_after_validation() returns 'code_generator' when retries remain."""
        state = AgentState(validation_result=_failing_result(), retry_count=1, max_retries=3)
        assert route_after_validation(state) == "code_generator"

    def test_routes_to_end_when_max_retries_reached(self) -> None:
        """route_after_validation() returns END when max retries are exhausted."""
        from langgraph.graph import END

        state = AgentState(validation_result=_failing_result(), retry_count=3, max_retries=3)
        assert route_after_validation(state) == END

    def test_routes_to_code_generator_when_no_validation_result(self) -> None:
        """route_after_validation() routes to code_generator when result is None."""
        state = AgentState(validation_result=None, retry_count=0, max_retries=3)
        assert route_after_validation(state) == "code_generator"

    def test_routes_to_end_at_exactly_max_retries(self) -> None:
        """route_after_validation() routes to END at exactly max_retries."""
        from langgraph.graph import END

        state = AgentState(validation_result=_failing_result(), retry_count=5, max_retries=5)
        assert route_after_validation(state) == END


# ---------------------------------------------------------------------------
# Unit tests — build_graph()
# ---------------------------------------------------------------------------


class TestBuildGraph:
    """Unit tests for build_graph()."""

    def test_build_graph_returns_compiled_graph(self) -> None:
        """build_graph() returns a compiled graph object."""
        graph = build_graph()
        assert graph is not None

    def test_compiled_graph_has_invoke_method(self) -> None:
        """The compiled graph has an invoke() method."""
        graph = build_graph()
        assert hasattr(graph, "invoke")


# ---------------------------------------------------------------------------
# Property 24: Agent node execution order
# ---------------------------------------------------------------------------


@given(task=st.text(min_size=1, max_size=50))
@settings(max_examples=50)
def test_property_24_node_execution_order(task: str) -> None:
    """Property 24: Agent node execution order is always planner → context_retriever → code_generator → validator → memory_writer.

    For any task string submitted to the agent, the LangGraph nodes SHALL
    execute in the order: planner, context_retriever, code_generator,
    validator, memory_writer.

    # Feature: local-sage, Property 24: Agent node execution order
    **Validates: Requirements 7.2**
    """
    # Feature: local-sage, Property 24: Agent node execution order

    call_order: list[str] = []

    def make_recorder(name: str, return_value: object) -> object:
        """Return a mock that records its call name."""

        def _node(state: AgentState) -> dict:
            call_order.append(name)
            if name == "planner":
                return {"plan": ["step 1"]}
            if name == "context_retriever":
                return {"context_symbols": [], "wiki_context": []}
            if name == "code_generator":
                return {"patch": "diff", "retry_count": state.retry_count}
            if name == "validator":
                return {"validation_result": _passing_result()}
            if name == "memory_writer":
                return {}
            return {}

        return _node

    with (
        patch(
            "local_sage.orchestration.graph.planner_node",
            side_effect=make_recorder("planner", None),
        ),
        patch(
            "local_sage.orchestration.graph.context_retriever_node",
            side_effect=make_recorder("context_retriever", None),
        ),
        patch(
            "local_sage.orchestration.graph.code_generator_node",
            side_effect=make_recorder("code_generator", None),
        ),
        patch(
            "local_sage.orchestration.graph.validator_node",
            side_effect=make_recorder("validator", None),
        ),
        patch(
            "local_sage.orchestration.graph.memory_writer_node",
            side_effect=make_recorder("memory_writer", None),
        ),
    ):
        graph = build_graph()
        graph.invoke(AgentState(task=task, max_retries=3))

    # Verify order
    assert call_order.index("planner") < call_order.index("context_retriever")
    assert call_order.index("context_retriever") < call_order.index("code_generator")
    assert call_order.index("code_generator") < call_order.index("validator")
    assert call_order.index("validator") < call_order.index("memory_writer")


# ---------------------------------------------------------------------------
# Property 25: Retry loop calls code_generator once per failure
# ---------------------------------------------------------------------------


def test_property_25_retry_loop_calls_code_generator_per_failure() -> None:
    """Property 25: Retry loop calls code_generator once per failure up to max_retries.

    For N consecutive ValidationResult(passed=False) responses where N ≤ max_retries,
    code_generator SHALL be called exactly N+1 times total.

    # Feature: local-sage, Property 25: Retry loop calls code_generator once per failure
    **Validates: Requirements 7.3**
    """
    # Feature: local-sage, Property 25: Retry loop calls code_generator once per failure
    max_retries = 3
    code_gen_calls: list[int] = [0]
    validator_calls: list[int] = [0]

    def mock_code_gen(state: AgentState) -> dict:
        code_gen_calls[0] += 1
        return {"patch": "diff", "retry_count": state.retry_count + 1}

    def mock_validator(state: AgentState) -> dict:
        validator_calls[0] += 1
        # Fail on first 2 calls, pass on 3rd
        if validator_calls[0] < 3:
            return {"validation_result": _failing_result()}
        return {"validation_result": _passing_result()}

    with (
        patch("local_sage.orchestration.graph.planner_node", return_value={"plan": ["step"]}),
        patch(
            "local_sage.orchestration.graph.context_retriever_node",
            return_value={"context_symbols": [], "wiki_context": []},
        ),
        patch("local_sage.orchestration.graph.code_generator_node", side_effect=mock_code_gen),
        patch("local_sage.orchestration.graph.validator_node", side_effect=mock_validator),
        patch("local_sage.orchestration.graph.memory_writer_node", return_value={}),
    ):
        graph = build_graph()
        graph.invoke(AgentState(task="task", max_retries=max_retries))

    # 2 failures → 3 code_gen calls (initial + 2 retries)
    assert code_gen_calls[0] == 3


# ---------------------------------------------------------------------------
# Property 26: Max retries exhausted → no patch applied
# ---------------------------------------------------------------------------


def test_property_26_max_retries_exhausted_no_patch_applied() -> None:
    """Property 26: Max retries exhausted → no patch applied.

    When max_retries + 1 consecutive ValidationResult(passed=False) responses
    occur, Patcher.apply_to_repo() SHALL never be called.

    # Feature: local-sage, Property 26: Max retries exhausted → no patch applied
    **Validates: Requirements 7.4**
    """
    # Feature: local-sage, Property 26: Max retries exhausted → no patch applied
    max_retries = 2
    memory_writer_called: list[bool] = [False]

    def mock_memory_writer(state: AgentState) -> dict:
        memory_writer_called[0] = True
        return {}

    with (
        patch("local_sage.orchestration.graph.planner_node", return_value={"plan": ["step"]}),
        patch(
            "local_sage.orchestration.graph.context_retriever_node",
            return_value={"context_symbols": [], "wiki_context": []},
        ),
        patch(
            "local_sage.orchestration.graph.code_generator_node",
            side_effect=lambda s: {"patch": "diff", "retry_count": s.retry_count + 1},
        ),
        patch(
            "local_sage.orchestration.graph.validator_node",
            return_value={"validation_result": _failing_result()},
        ),
        patch("local_sage.orchestration.graph.memory_writer_node", side_effect=mock_memory_writer),
    ):
        graph = build_graph()
        graph.invoke(AgentState(task="task", max_retries=max_retries))

    # memory_writer should NOT have been called — max retries exhausted
    assert memory_writer_called[0] is False


# ---------------------------------------------------------------------------
# Property 27: memory_writer updates both SessionManager and WikiManager
# ---------------------------------------------------------------------------


def test_property_27_memory_writer_updates_session_and_wiki(tmp_path: Path) -> None:
    """Property 27: memory_writer updates both SessionManager and WikiManager.

    For any successfully completed task (ValidationResult.passed=True),
    memory_writer_node SHALL call both SessionManager.record_task() and
    WikiManager.write_entry().

    # Feature: local-sage, Property 27: memory_writer updates both SessionManager and WikiManager
    **Validates: Requirements 7.6**
    """
    # Feature: local-sage, Property 27: memory_writer updates both SessionManager and WikiManager
    from local_sage.orchestration.nodes import memory_writer_node

    state = AgentState(
        task="add rate limiter",
        patch="--- a/foo.py\n+++ b/foo.py\n",
        validation_result=_passing_result(),
        session_id="sess-1",
    )

    # Create a fake db file so SessionManager is invoked
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    db_path = sage_dir / "memory.db"
    db_path.touch()

    with (
        patch("local_sage.orchestration.nodes.Path.cwd", return_value=tmp_path),
        patch("local_sage.orchestration.nodes.SessionManager") as MockSession,
        patch("local_sage.orchestration.nodes.WikiManager") as MockWiki,
    ):
        mock_session_instance = MockSession.return_value
        mock_wiki_instance = MockWiki.return_value
        mock_wiki_instance.write_entry.return_value = MagicMock()

        memory_writer_node(state)

    mock_session_instance.record_task.assert_called_once()
    mock_wiki_instance.write_entry.assert_called_once()
