"""Semantic memory for local-sage using Mem0 with a HuggingFace embedder.

This module provides:
- ``MEM0_CONFIG`` — Mem0 configuration dict (HuggingFace embedder, Ollama LLM,
  Qdrant vector store).  This is the single source of truth for the embedder
  provider; it MUST remain ``"huggingface"`` at all times.
- ``SemanticMemory`` — thin wrapper around ``mem0.Memory`` that scopes
  observations to the current repository via a stable ``user_id``.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mem0 configuration
# ---------------------------------------------------------------------------

# CRITICAL: embedder.provider MUST be "huggingface".  Do NOT change this to
# "openai", "cohere", or any other cloud provider.  The sentence-transformers
# model runs entirely in-process and requires no external API key.
MEM0_CONFIG: dict[str, Any] = {
    "embedder": {
        "provider": "huggingface",
        "config": {
            "model": "multi-qa-MiniLM-L6-cos-v1",
            "embedding_dims": 384,
        },
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "qwen2.5-coder:7b-instruct-q4_K_M",
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "local_sage",
            "path": ".sage/vectors",
        },
    },
}


# ---------------------------------------------------------------------------
# SemanticMemory
# ---------------------------------------------------------------------------


class SemanticMemory:
    """Semantic memory backed by Mem0 with a HuggingFace sentence-transformer.

    Observations are stored in a Qdrant on-disk vector store and retrieved via
    approximate nearest-neighbour search.  Each repository gets its own
    ``user_id`` derived from the repository root path so that memories from
    different repos never mix.

    No OpenAI key is required or used.

    Attributes:
        _memory: The underlying ``mem0.Memory`` instance.
        _user_id: Stable 8-character hex identifier scoped to *repo_root*.

    Example::

        mem = SemanticMemory(Path("/home/user/my-project"))
        mem.add_observation("Prefer async functions in the API layer.")
        results = mem.search("async patterns", top_k=3)
    """

    def __init__(self, repo_root: Path) -> None:
        """Initialise SemanticMemory for the given repository root.

        Computes a stable ``user_id`` from *repo_root* and initialises the
        Mem0 ``Memory`` instance with ``MEM0_CONFIG``.

        Args:
            repo_root: Absolute path to the repository root.  Used to derive
                the ``user_id`` that scopes all stored observations.
        """
        from mem0 import Memory  # noqa: PLC0415 — deferred to avoid import-time side effects

        self._user_id: str = _compute_user_id(repo_root)
        logger.debug(
            "SemanticMemory initialised for repo %s (user_id=%s)",
            repo_root,
            self._user_id,
        )
        self._memory: Memory = Memory.from_config(MEM0_CONFIG)

    def add_observation(self, text: str, user_id: str | None = None) -> None:
        """Store a free-text observation in semantic memory.

        Args:
            text: The observation text to embed and store.
            user_id: Optional override for the repository-scoped ``user_id``.
                Callers should not normally supply this; it exists for testing
                and cross-repo scenarios.
        """
        effective_user_id = user_id or self._user_id
        logger.debug("Adding observation for user_id=%s: %.80s…", effective_user_id, text)
        self._memory.add(text, user_id=effective_user_id)

    def search(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[str]:
        """Search semantic memory for observations relevant to *query*.

        Args:
            query: Natural-language search query.
            user_id: Optional override for the repository-scoped ``user_id``.
                Callers should not normally supply this.
            top_k: Maximum number of results to return.  Defaults to 5.

        Returns:
            A list of up to *top_k* observation strings, ordered by relevance
            (most relevant first).
        """
        effective_user_id = user_id or self._user_id
        logger.debug(
            "Searching semantic memory for user_id=%s, query=%.80s…",
            effective_user_id,
            query,
        )
        result = self._memory.search(query, user_id=effective_user_id, limit=top_k)
        return [item["memory"] for item in result.get("results", [])]


# ---------------------------------------------------------------------------
# Module-level helpers (private)
# ---------------------------------------------------------------------------


def _compute_user_id(repo_root: Path) -> str:
    """Derive a stable 8-character hex user ID from *repo_root*.

    The ID is the first 8 hex characters of the SHA-256 digest of the
    string representation of *repo_root*.  This is stable across process
    restarts and unique enough to avoid collisions between different repos.

    Args:
        repo_root: Absolute path to the repository root.

    Returns:
        An 8-character lowercase hex string.
    """
    return hashlib.sha256(str(repo_root).encode()).hexdigest()[:8]
