"""Unit tests for LangGraph node functions (Layer 2 — Orchestration).

Each node is tested in isolation with mocked dependencies.

**Validates: Requirements 7.1, 7.2, 7.3, 7.6**
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from local_sage.model.client import ModelResponse
from local_sage.orchestration.nodes import (
    code_generator_node,
    context_retriever_node,
    memory_writer_node,
    planner_node,
    validator_node,
)
from local_sage.orchestration.state import AgentState
from local_sage.repo_graph.graph import SymbolGraph
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


def _mock_response(text: str) -> ModelResponse:
    """Return a ModelResponse with the given text."""
    return ModelResponse(
        text=text,
        tokens_used=10,
        prompt_tokens=5,
        finish_reason="stop",
        duration_ms=100,
    )


# ---------------------------------------------------------------------------
# planner_node
# ---------------------------------------------------------------------------


class TestPlannerNode:
    """Unit tests for planner_node()."""

    def test_returns_plan_list(self) -> None:
        """planner_node() returns a dict with a non-empty 'plan' list."""
        state = AgentState(task="add rate limiter")
        mock_response = _mock_response("1. Design the limiter\n2. Implement it\n3. Test it")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(return_value=mock_response)
            result = planner_node(state)

        assert "plan" in result
        assert isinstance(result["plan"], list)
        assert len(result["plan"]) > 0

    def test_falls_back_to_single_step_on_error(self) -> None:
        """planner_node() returns a single-step plan when OllamaClient fails."""
        state = AgentState(task="add rate limiter")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(side_effect=Exception("connection refused"))
            result = planner_node(state)

        assert "plan" in result
        assert len(result["plan"]) == 1
        assert "add rate limiter" in result["plan"][0]

    def test_filters_empty_lines_from_plan(self) -> None:
        """planner_node() filters out blank lines from the model response."""
        state = AgentState(task="task")
        mock_response = _mock_response("step 1\n\nstep 2\n\n")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(return_value=mock_response)
            result = planner_node(state)

        assert "" not in result["plan"]


# ---------------------------------------------------------------------------
# context_retriever_node
# ---------------------------------------------------------------------------


class TestContextRetrieverNode:
    """Unit tests for context_retriever_node()."""

    def test_returns_context_symbols_and_wiki_context(self, tmp_path: Path) -> None:
        """context_retriever_node() returns context_symbols and wiki_context."""
        state = AgentState(task="add rate limiter", plan=["step 1"])

        with (
            patch("local_sage.orchestration.nodes.Path.cwd", return_value=tmp_path),
            patch("local_sage.orchestration.nodes._load_graph", return_value=SymbolGraph()),
            patch("local_sage.orchestration.nodes.ContextSelector") as MockSelector,
            patch("local_sage.orchestration.nodes.WikiManager") as MockWiki,
        ):
            MockSelector.return_value.select.return_value = []
            MockWiki.return_value.search_entries.return_value = []
            result = context_retriever_node(state)

        assert "context_symbols" in result
        assert "wiki_context" in result
        assert isinstance(result["context_symbols"], list)
        assert isinstance(result["wiki_context"], list)


# ---------------------------------------------------------------------------
# code_generator_node
# ---------------------------------------------------------------------------


class TestCodeGeneratorNode:
    """Unit tests for code_generator_node()."""

    def test_returns_patch_string(self) -> None:
        """code_generator_node() returns a dict with a 'patch' string."""
        state = AgentState(task="add rate limiter")
        mock_response = _mock_response("--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(return_value=mock_response)
            result = code_generator_node(state)

        assert "patch" in result
        assert isinstance(result["patch"], str)

    def test_increments_retry_count_on_retry(self) -> None:
        """code_generator_node() increments retry_count when validation_result is set."""
        state = AgentState(task="task", retry_count=1, validation_result=_failing_result())
        mock_response = _mock_response("diff")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(return_value=mock_response)
            result = code_generator_node(state)

        assert result["retry_count"] == 2

    def test_does_not_increment_retry_count_on_first_attempt(self) -> None:
        """code_generator_node() does not increment retry_count on first attempt."""
        state = AgentState(task="task", retry_count=0, validation_result=None)
        mock_response = _mock_response("diff")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(return_value=mock_response)
            result = code_generator_node(state)

        assert result["retry_count"] == 0

    def test_returns_empty_patch_on_error(self) -> None:
        """code_generator_node() returns empty patch when OllamaClient fails."""
        state = AgentState(task="task")

        with patch("local_sage.orchestration.nodes.OllamaClient") as MockClient:
            instance = MockClient.return_value
            instance.generate = AsyncMock(side_effect=Exception("timeout"))
            result = code_generator_node(state)

        assert result["patch"] == ""


# ---------------------------------------------------------------------------
# validator_node
# ---------------------------------------------------------------------------


class TestValidatorNode:
    """Unit tests for validator_node()."""

    def test_returns_validation_result(self, tmp_path: Path) -> None:
        """validator_node() returns a dict with a 'validation_result'."""
        state = AgentState(patch="--- a/foo.py\n+++ b/foo.py\n")

        with (
            patch("local_sage.orchestration.nodes.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.runner.ValidationRunner") as MockRunner,
        ):
            MockRunner.return_value.validate_only.return_value = _passing_result()
            result = validator_node(state)

        assert "validation_result" in result
        assert isinstance(result["validation_result"], ValidationResult)

    def test_returns_failing_result_on_exception(self, tmp_path: Path) -> None:
        """validator_node() returns a failing result when ValidationRunner raises."""
        state = AgentState(patch="bad patch")

        with (
            patch("local_sage.orchestration.nodes.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.runner.ValidationRunner") as MockRunner,
        ):
            MockRunner.return_value.validate_only.side_effect = Exception("crash")
            result = validator_node(state)

        assert result["validation_result"].passed is False


# ---------------------------------------------------------------------------
# memory_writer_node
# ---------------------------------------------------------------------------


class TestMemoryWriterNode:
    """Unit tests for memory_writer_node()."""

    def test_returns_empty_dict(self, tmp_path: Path) -> None:
        """memory_writer_node() returns an empty dict (side-effects only)."""
        state = AgentState(
            task="add rate limiter",
            patch="diff",
            validation_result=_passing_result(),
            session_id="sess-1",
        )

        with (
            patch("local_sage.orchestration.nodes.Path.cwd", return_value=tmp_path),
            patch("local_sage.orchestration.nodes.SessionManager"),
            patch("local_sage.orchestration.nodes.WikiManager") as MockWiki,
        ):
            MockWiki.return_value.write_entry.return_value = MagicMock()
            result = memory_writer_node(state)

        assert result == {}

    def test_calls_wiki_manager_write_entry(self, tmp_path: Path) -> None:
        """memory_writer_node() calls WikiManager.write_entry()."""
        state = AgentState(
            task="add rate limiter",
            patch="diff",
            validation_result=_passing_result(),
            session_id="",
        )

        with (
            patch("local_sage.orchestration.nodes.Path.cwd", return_value=tmp_path),
            patch("local_sage.orchestration.nodes.WikiManager") as MockWiki,
        ):
            mock_instance = MockWiki.return_value
            mock_instance.write_entry.return_value = MagicMock()
            memory_writer_node(state)

        mock_instance.write_entry.assert_called_once()
