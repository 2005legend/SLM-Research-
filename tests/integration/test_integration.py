"""Integration tests for local-sage.

All tests in this module require ``SAGE_INTEGRATION=true`` to be set.
They exercise the full system with real filesystem operations and
subprocess calls, using a mocked OllamaClient to avoid needing Ollama.

Run with:
    SAGE_INTEGRATION=true pytest tests/integration/ -v
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

from local_sage.model.client import ModelResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_REPO = Path(__file__).parent / "fixture_repo"


def _mock_model_response(text: str = "") -> ModelResponse:
    """Return a ModelResponse with the given text.

    Args:
        text: Generated text to return.

    Returns:
        A ModelResponse instance.
    """
    return ModelResponse(
        text=text,
        tokens_used=10,
        prompt_tokens=5,
        finish_reason="stop",
        duration_ms=100,
    )


def _copy_fixture_repo(dest: Path) -> Path:
    """Copy the fixture repository to *dest* and return the copy path.

    Args:
        dest: Destination directory (must not exist).

    Returns:
        Path to the copied repository root.
    """
    repo_copy = dest / "fixture_repo"
    shutil.copytree(_FIXTURE_REPO, repo_copy)
    return repo_copy


# ---------------------------------------------------------------------------
# 29.3 Integration test: full sage start on fixture repo
# ---------------------------------------------------------------------------


def test_sage_start_indexes_fixture_repo(require_integration: None, tmp_path: Path) -> None:
    """sage start indexes the fixture repo and creates a session.

    Requires: SAGE_INTEGRATION=true
    Mocks: OllamaClient (no Ollama server needed)

    **Validates: Requirements 1.2, 3.1, 4.1**
    """
    repo = _copy_fixture_repo(tmp_path)
    sage_dir = repo / ".sage"
    sage_dir.mkdir()

    from local_sage.memory.session import SessionManager
    from local_sage.repo_graph.indexer import RepoIndexer

    # Index the repo
    indexer = RepoIndexer()
    graph = indexer.index_repo(repo)
    cache_path = sage_dir / "index.json"
    indexer.save_index(graph, cache_path)

    # Verify index was created
    assert cache_path.exists()
    loaded = indexer.load_index(cache_path)
    assert loaded is not None
    assert len(list(loaded._graph.nodes)) > 0

    # Create a session
    db_path = sage_dir / "memory.db"
    sm = SessionManager(db_path)
    session_id = sm.create_session(repo)
    assert session_id
    session = sm.load_latest_session(repo)
    assert session is not None
    assert session.session_id == session_id


# ---------------------------------------------------------------------------
# 29.4 Integration test: full sage task with mocked OllamaClient
# ---------------------------------------------------------------------------


def test_sage_task_with_mocked_ollama(require_integration: None, tmp_path: Path) -> None:
    """sage task runs the full agent loop with a mocked OllamaClient.

    Requires: SAGE_INTEGRATION=true
    Mocks: OllamaClient.generate (returns a no-op patch)

    **Validates: Requirements 7.1, 7.2**
    """
    repo = _copy_fixture_repo(tmp_path)
    sage_dir = repo / ".sage"
    sage_dir.mkdir()

    # Pre-index the repo
    from local_sage.repo_graph.indexer import RepoIndexer

    indexer = RepoIndexer()
    graph = indexer.index_repo(repo)
    indexer.save_index(graph, sage_dir / "index.json")

    # Create a session
    from local_sage.memory.session import SessionManager

    sm = SessionManager(sage_dir / "memory.db")
    session_id = sm.create_session(repo)

    # Run the agent loop with mocked Ollama
    from local_sage.orchestration.graph import build_graph
    from local_sage.orchestration.state import AgentState

    plan_response = _mock_model_response("1. Add divide function\n2. Write tests")
    patch_response = _mock_model_response("")  # empty patch — no-op

    with (
        patch("local_sage.orchestration.nodes.Path.cwd", return_value=repo),
        patch("local_sage.orchestration.nodes.OllamaClient") as MockClient,
    ):
        instance = MockClient.return_value
        instance.generate = AsyncMock(side_effect=[plan_response, patch_response])

        graph = build_graph()
        final = graph.invoke(
            AgentState(
                task="add a divide function",
                max_retries=1,
                session_id=session_id,
            )
        )

    # Agent should have run without crashing
    assert final is not None


# ---------------------------------------------------------------------------
# 29.5 Integration test: ValidationRunner end-to-end with real tools
# ---------------------------------------------------------------------------


def test_validation_runner_end_to_end(require_integration: None, tmp_path: Path) -> None:
    """ValidationRunner runs real pytest/mypy/ruff on the fixture repo.

    Requires: SAGE_INTEGRATION=true
    Does NOT mock subprocesses — runs real pytest, mypy, ruff.

    **Validates: Requirements 6.1, 6.4, 6.5, 6.6**
    """
    repo = _copy_fixture_repo(tmp_path)

    from local_sage.validation.runner import ValidationRunner

    runner = ValidationRunner(
        repo_root=repo,
        manual_review=False,
        pytest_timeout=60,
        mypy_timeout=60,
        ruff_timeout=30,
    )

    # An empty patch should not break anything
    result = runner.validate_only("")

    # Result should be a ValidationResult (pass or fail — both are valid)
    assert result is not None
    assert isinstance(result.passed, bool)
    assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# 29.6 Integration test: memory_writer calls both SessionManager and WikiManager
# ---------------------------------------------------------------------------


def test_memory_writer_updates_session_and_wiki(require_integration: None, tmp_path: Path) -> None:
    """memory_writer_node calls both SessionManager.record_task() and WikiManager.write_entry().

    Requires: SAGE_INTEGRATION=true

    **Validates: Requirements 7.6**
    """
    repo = _copy_fixture_repo(tmp_path)
    sage_dir = repo / ".sage"
    sage_dir.mkdir()
    wiki_dir = repo / "wiki"

    from local_sage.memory.session import SessionManager
    from local_sage.orchestration.nodes import memory_writer_node
    from local_sage.orchestration.state import AgentState
    from local_sage.validation.result import (
        PytestCounts,
        ValidationResult,
    )

    # Set up session
    sm = SessionManager(sage_dir / "memory.db")
    session_id = sm.create_session(repo)

    result = ValidationResult(
        passed=True,
        failures=[],
        pytest_counts=PytestCounts(passed=3, failed=0, errors=0),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=500,
    )

    state = AgentState(
        task="add divide function",
        patch="--- a/calculator.py\n+++ b/calculator.py\n",
        validation_result=result,
        session_id=session_id,
    )

    with patch("local_sage.orchestration.nodes.Path.cwd", return_value=repo):
        memory_writer_node(state)

    # Verify session was updated
    summary = sm.get_session_summary(session_id)
    assert summary.task_count == 1
    assert summary.patch_count >= 1

    # Verify wiki entry was written
    assert wiki_dir.exists()
    wiki_files = list(wiki_dir.glob("*.md"))
    assert len(wiki_files) >= 1
