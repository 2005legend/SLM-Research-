"""Unit tests for AgentState (Layer 2 — Orchestration).

Covers field defaults, type correctness, and dataclass construction.

**Validates: Requirements 7.5**
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from local_sage.orchestration.state import AgentState
from local_sage.repo_graph.graph import SymbolInfo
from local_sage.validation.result import (
    PytestCounts,
    ValidationResult,
)
from local_sage.wiki.manager import WikiEntry


class TestAgentStateDefaults:
    """Unit tests for AgentState default field values."""

    def test_task_defaults_to_empty_string(self) -> None:
        """AgentState.task defaults to ''."""
        state = AgentState()
        assert state.task == ""

    def test_plan_defaults_to_empty_list(self) -> None:
        """AgentState.plan defaults to []."""
        state = AgentState()
        assert state.plan == []

    def test_context_symbols_defaults_to_empty_list(self) -> None:
        """AgentState.context_symbols defaults to []."""
        state = AgentState()
        assert state.context_symbols == []

    def test_wiki_context_defaults_to_empty_list(self) -> None:
        """AgentState.wiki_context defaults to []."""
        state = AgentState()
        assert state.wiki_context == []

    def test_patch_defaults_to_none(self) -> None:
        """AgentState.patch defaults to None."""
        state = AgentState()
        assert state.patch is None

    def test_validation_result_defaults_to_none(self) -> None:
        """AgentState.validation_result defaults to None."""
        state = AgentState()
        assert state.validation_result is None

    def test_retry_count_defaults_to_zero(self) -> None:
        """AgentState.retry_count defaults to 0."""
        state = AgentState()
        assert state.retry_count == 0

    def test_max_retries_defaults_to_three(self) -> None:
        """AgentState.max_retries defaults to 3."""
        state = AgentState()
        assert state.max_retries == 3

    def test_session_id_defaults_to_empty_string(self) -> None:
        """AgentState.session_id defaults to ''."""
        state = AgentState()
        assert state.session_id == ""

    def test_error_defaults_to_none(self) -> None:
        """AgentState.error defaults to None."""
        state = AgentState()
        assert state.error is None


class TestAgentStateConstruction:
    """Unit tests for AgentState construction with explicit values."""

    def _make_symbol(self) -> SymbolInfo:
        """Return a minimal SymbolInfo for testing."""
        return SymbolInfo(
            name="my_func",
            kind="function",
            file_path=Path("pkg/mod.py"),
            start_byte=0,
            end_byte=50,
            start_line=1,
            end_line=5,
            source="def my_func(): pass",
        )

    def _make_wiki_entry(self) -> WikiEntry:
        """Return a minimal WikiEntry for testing."""
        return WikiEntry(
            title="Test Entry",
            file_path=Path("wiki/test_entry.md"),
            content="# Test",
            last_modified=datetime.now(tz=UTC),
        )

    def _make_validation_result(self) -> ValidationResult:
        """Return a passing ValidationResult for testing."""
        return ValidationResult(
            passed=True,
            failures=[],
            pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
            mypy_errors=[],
            ruff_violations=[],
            contract_failures=[],
            duration_ms=100,
        )

    def test_construction_with_all_fields(self) -> None:
        """AgentState can be constructed with all fields explicitly set."""
        symbol = self._make_symbol()
        entry = self._make_wiki_entry()
        result = self._make_validation_result()

        state = AgentState(
            task="add rate limiter",
            plan=["step 1", "step 2"],
            context_symbols=[symbol],
            wiki_context=[entry],
            patch="--- a/foo.py\n+++ b/foo.py\n",
            validation_result=result,
            retry_count=1,
            max_retries=3,
            session_id="abc-123",
            error=None,
        )

        assert state.task == "add rate limiter"
        assert len(state.plan) == 2
        assert len(state.context_symbols) == 1
        assert len(state.wiki_context) == 1
        assert state.patch is not None
        assert state.validation_result is not None
        assert state.retry_count == 1
        assert state.session_id == "abc-123"

    def test_context_symbols_accepts_symbol_info_list(self) -> None:
        """AgentState.context_symbols accepts a list of SymbolInfo objects."""
        symbols = [self._make_symbol(), self._make_symbol()]
        state = AgentState(context_symbols=symbols)
        assert len(state.context_symbols) == 2
        assert all(isinstance(s, SymbolInfo) for s in state.context_symbols)

    def test_wiki_context_accepts_wiki_entry_list(self) -> None:
        """AgentState.wiki_context accepts a list of WikiEntry objects."""
        entries = [self._make_wiki_entry()]
        state = AgentState(wiki_context=entries)
        assert len(state.wiki_context) == 1
        assert isinstance(state.wiki_context[0], WikiEntry)

    def test_validation_result_accepts_validation_result(self) -> None:
        """AgentState.validation_result accepts a ValidationResult object."""
        result = self._make_validation_result()
        state = AgentState(validation_result=result)
        assert isinstance(state.validation_result, ValidationResult)
        assert state.validation_result.passed is True

    def test_independent_default_lists(self) -> None:
        """Two AgentState instances do not share the same default list objects."""
        a = AgentState()
        b = AgentState()
        a.plan.append("step")
        assert b.plan == []
