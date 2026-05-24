"""Unit and property-based tests for SemanticMemory (Layer 4 — Session Memory).

Tests cover MEM0_CONFIG correctness, user_id stability, add/search delegation,
result extraction, and Property 15 (add-then-search round-trip with localhost
HTTP constraint).

All tests mock ``mem0.Memory`` to avoid requiring the actual mem0 package or
a running Qdrant / Ollama instance.  Because ``SemanticMemory.__init__`` uses
a deferred ``from mem0 import Memory`` import, we inject a fake ``mem0`` module
into ``sys.modules`` before constructing any ``SemanticMemory`` instance.

**Validates: Requirements 4.4, 4.5**
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from local_sage.memory.semantic import MEM0_CONFIG, _compute_user_id

# ---------------------------------------------------------------------------
# Fake mem0 module injection
# ---------------------------------------------------------------------------


def _inject_fake_mem0() -> MagicMock:
    """Inject a fake ``mem0`` module into sys.modules and return the mock Memory class.

    Because ``SemanticMemory.__init__`` does ``from mem0 import Memory`` as a
    deferred import, ``patch("mem0.Memory")`` only works if the ``mem0`` module
    is already importable.  When mem0 is not installed we inject a fake module
    directly into ``sys.modules``.

    Returns:
        The ``MagicMock`` that stands in for ``mem0.Memory``.
    """
    fake_mem0 = types.ModuleType("mem0")
    MockMemory = MagicMock()
    fake_mem0.Memory = MockMemory  # type: ignore[attr-defined]
    sys.modules["mem0"] = fake_mem0
    return MockMemory


def _make_mock_memory_instance(search_results: list[dict] | None = None) -> MagicMock:
    """Return a mock mem0.Memory *instance* pre-configured for testing.

    Args:
        search_results: List of result dicts to return from ``search()``.
            Each dict should have a ``"memory"`` key.  Defaults to an empty
            results list.

    Returns:
        A ``MagicMock`` whose ``search()`` returns the given results wrapped
        in ``{"results": [...]}`` and whose ``add()`` is a no-op.
    """
    mock = MagicMock()
    mock.search.return_value = {"results": search_results or []}
    mock.add.return_value = None
    return mock


def _make_semantic_memory(
    repo_root: Path,
    mock_memory_instance: MagicMock,
) -> SemanticMemory:  # noqa: F821
    """Construct a SemanticMemory with a fake mem0 module injected.

    Args:
        repo_root: Repository root path passed to SemanticMemory.
        mock_memory_instance: Pre-configured mock to use as the Memory instance.

    Returns:
        A SemanticMemory instance backed by *mock_memory_instance*.
    """
    from local_sage.memory.semantic import SemanticMemory

    MockMemory = _inject_fake_mem0()
    MockMemory.from_config.return_value = mock_memory_instance
    return SemanticMemory(repo_root)


# ---------------------------------------------------------------------------
# Import SemanticMemory after helpers are defined
# ---------------------------------------------------------------------------

# We import SemanticMemory here (not at module top) so that the fake mem0
# injection in _make_semantic_memory() happens before any __init__ call.
# The MEM0_CONFIG and _compute_user_id imports above are safe because they
# don't trigger the deferred mem0 import.
from local_sage.memory.semantic import SemanticMemory  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests — MEM0_CONFIG correctness
# ---------------------------------------------------------------------------


class TestMem0Config:
    """Unit tests verifying MEM0_CONFIG uses only local, privacy-safe providers."""

    def test_mem0_config_uses_huggingface_embedder(self) -> None:
        """MEM0_CONFIG embedder.provider must be 'huggingface'.

        This is the critical privacy constraint: no cloud embedding provider
        may ever be configured.
        """
        assert MEM0_CONFIG["embedder"]["provider"] == "huggingface", (
            "embedder.provider MUST be 'huggingface' — never a cloud provider"
        )

    def test_mem0_config_uses_ollama_llm(self) -> None:
        """MEM0_CONFIG llm.provider must be 'ollama'."""
        assert MEM0_CONFIG["llm"]["provider"] == "ollama"

    def test_mem0_config_ollama_url_is_localhost(self) -> None:
        """MEM0_CONFIG llm.config.ollama_base_url must point to localhost:11434."""
        assert MEM0_CONFIG["llm"]["config"]["ollama_base_url"] == "http://localhost:11434"

    def test_mem0_config_uses_qdrant_vector_store(self) -> None:
        """MEM0_CONFIG vector_store.provider must be 'qdrant'."""
        assert MEM0_CONFIG["vector_store"]["provider"] == "qdrant"

    def test_mem0_config_embedder_model_is_set(self) -> None:
        """MEM0_CONFIG embedder.config.model must be the expected sentence-transformer."""
        assert MEM0_CONFIG["embedder"]["config"]["model"] == "multi-qa-MiniLM-L6-cos-v1"

    def test_mem0_config_embedding_dims_is_384(self) -> None:
        """MEM0_CONFIG embedder.config.embedding_dims must be 384."""
        assert MEM0_CONFIG["embedder"]["config"]["embedding_dims"] == 384


# ---------------------------------------------------------------------------
# Unit tests — user_id stability
# ---------------------------------------------------------------------------


class TestUserIdStability:
    """Unit tests for the stable user_id derived from repo_root."""

    def test_user_id_is_stable(self, tmp_path: Path) -> None:
        """The same repo_root always produces the same user_id.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        repo_root = tmp_path / "my_repo"
        id1 = _compute_user_id(repo_root)
        id2 = _compute_user_id(repo_root)
        assert id1 == id2

    def test_user_id_is_eight_hex_chars(self, tmp_path: Path) -> None:
        """user_id is exactly 8 lowercase hex characters.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        repo_root = tmp_path / "my_repo"
        user_id = _compute_user_id(repo_root)
        assert len(user_id) == 8
        assert all(c in "0123456789abcdef" for c in user_id)

    def test_user_id_differs_for_different_repos(self, tmp_path: Path) -> None:
        """Different repo_roots produce different user_ids.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        assert _compute_user_id(repo_a) != _compute_user_id(repo_b)


# ---------------------------------------------------------------------------
# Unit tests — add_observation
# ---------------------------------------------------------------------------


class TestAddObservation:
    """Unit tests for SemanticMemory.add_observation()."""

    def test_add_observation_calls_memory_add(self, tmp_path: Path) -> None:
        """add_observation() calls Memory.add() with the correct text and user_id.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        mock_instance = _make_mock_memory_instance()
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        mem.add_observation("Prefer async functions")

        mock_instance.add.assert_called_once_with(
            "Prefer async functions",
            user_id=_compute_user_id(repo_root),
        )

    def test_add_observation_uses_custom_user_id_when_provided(self, tmp_path: Path) -> None:
        """add_observation() uses the supplied user_id override when given.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        mock_instance = _make_mock_memory_instance()
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        mem.add_observation("some text", user_id="custom_id")

        mock_instance.add.assert_called_once_with("some text", user_id="custom_id")


# ---------------------------------------------------------------------------
# Unit tests — search
# ---------------------------------------------------------------------------


class TestSearch:
    """Unit tests for SemanticMemory.search()."""

    def test_search_calls_memory_search(self, tmp_path: Path) -> None:
        """search() calls Memory.search() with the correct query and user_id.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        mock_instance = _make_mock_memory_instance()
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        mem.search("async patterns")

        mock_instance.search.assert_called_once_with(
            "async patterns",
            user_id=_compute_user_id(repo_root),
            limit=5,
        )

    def test_search_extracts_memory_field(self, tmp_path: Path) -> None:
        """search() extracts the 'memory' field from each result dict.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        results = [
            {"memory": "Prefer async functions", "score": 0.9},
            {"memory": "Use pathlib for file I/O", "score": 0.7},
        ]
        mock_instance = _make_mock_memory_instance(search_results=results)
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        output = mem.search("file handling")

        assert output == ["Prefer async functions", "Use pathlib for file I/O"]

    def test_search_returns_empty_list_when_no_results(self, tmp_path: Path) -> None:
        """search() returns an empty list when Memory.search() returns no results.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        mock_instance = _make_mock_memory_instance(search_results=[])
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        output = mem.search("anything")

        assert output == []

    def test_search_respects_top_k_parameter(self, tmp_path: Path) -> None:
        """search() passes top_k as the limit argument to Memory.search().

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        mock_instance = _make_mock_memory_instance()
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        mem.search("query", top_k=3)

        mock_instance.search.assert_called_once_with(
            "query",
            user_id=_compute_user_id(repo_root),
            limit=3,
        )

    def test_search_uses_custom_user_id_when_provided(self, tmp_path: Path) -> None:
        """search() uses the supplied user_id override when given.

        Args:
            tmp_path: Pytest fixture providing a temporary directory.
        """
        mock_instance = _make_mock_memory_instance()
        repo_root = tmp_path / "repo"
        mem = _make_semantic_memory(repo_root, mock_instance)
        mem.search("query", user_id="override_id")

        mock_instance.search.assert_called_once_with(
            "query",
            user_id="override_id",
            limit=5,
        )


# ---------------------------------------------------------------------------
# Property 15: Semantic memory add-then-search round-trip
# ---------------------------------------------------------------------------


@given(observation=st.text(min_size=1, max_size=300))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_15_semantic_memory_add_then_search_round_trip(
    observation: str, tmp_path: Path
) -> None:
    """Property 15: Semantic memory add-then-search round-trip.

    For any observation text string, calling SemanticMemory.add_observation()
    followed by SemanticMemory.search() with the same text as the query SHALL
    return a result list containing at least one entry whose content matches
    the added observation.

    Additionally, no HTTP request SHALL be made to any endpoint other than
    localhost:11434.  This is verified by asserting that mem0.Memory is
    configured with embedder.provider = "huggingface" (so no cloud embedding
    calls are made) and by confirming that MEM0_CONFIG contains no non-local
    URL.

    # Feature: local-sage, Property 15: Semantic memory add-then-search round-trip

    **Validates: Requirements 4.4, 4.5**

    Args:
        observation: Arbitrary observation text generated by Hypothesis.
        tmp_path: Pytest fixture providing a temporary directory.
    """
    # Property 15: Semantic memory add-then-search round-trip
    repo_root = tmp_path / "repo"

    # --- Part 1: add-then-search round-trip ---
    # The mock returns the observation as a search result, simulating a
    # correctly functioning vector store.
    mock_instance = _make_mock_memory_instance(
        search_results=[{"memory": observation, "score": 1.0}]
    )
    MockMemory = _inject_fake_mem0()
    MockMemory.from_config.return_value = mock_instance

    mem = SemanticMemory(repo_root)
    mem.add_observation(observation)
    results = mem.search(observation)

    # The search result list must contain at least one entry matching the observation
    assert len(results) >= 1, (
        f"Expected at least one search result after add_observation(), got {results!r}"
    )
    assert observation in results, (
        f"Expected observation {observation!r} to appear in search results {results!r}"
    )

    # --- Part 2: no non-localhost HTTP calls ---
    # Verify that MEM0_CONFIG does not reference any non-localhost URL.
    # The embedder must be "huggingface" (in-process, no HTTP calls).
    assert MEM0_CONFIG["embedder"]["provider"] == "huggingface", (
        "embedder.provider MUST be 'huggingface' — cloud providers make outbound HTTP calls"
    )

    # The LLM must target only localhost:11434.
    llm_url: str = MEM0_CONFIG["llm"]["config"]["ollama_base_url"]
    assert llm_url.startswith("http://localhost:11434"), (
        f"LLM base URL must target localhost:11434, got: {llm_url!r}"
    )

    # Verify Memory.from_config was called with the correct config dict
    # (so the real mem0 would use our local-only config).
    MockMemory.from_config.assert_called_with(MEM0_CONFIG)
