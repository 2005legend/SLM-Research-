"""LangGraph node functions for Layer 2 — Orchestration.

Each node is a pure function ``(state: AgentState) -> dict[str, Any]``
that returns only the fields it modifies.  LangGraph merges the returned
dict back into the full ``AgentState``.

Node execution order:
    planner → context_retriever → code_generator → validator → memory_writer
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from local_sage.config import SageConfig, load_config
from local_sage.memory.session import SessionManager
from local_sage.model.client import OllamaClient
from local_sage.orchestration.state import AgentState
from local_sage.repo_graph.graph import SymbolGraph
from local_sage.repo_graph.selector import ContextSelector
from local_sage.wiki.manager import WikiManager

logger = logging.getLogger(__name__)


def planner_node(state: AgentState) -> dict[str, Any]:
    """Generate a high-level plan from the task description.

    Calls ``OllamaClient.generate()`` with a planning prompt and splits the
    response into a list of sub-task strings.  Each non-empty line in the
    model response becomes one plan step.

    Args:
        state: Current agent state.  Reads ``state.task``.

    Returns:
        A dict with ``"plan"`` set to a list of plan step strings.
    """
    import asyncio

    load_config()
    client = OllamaClient()
    system = (
        "You are a senior software engineer. "
        "Given a coding task, produce a numbered list of concrete implementation steps. "
        "Output one step per line. Be concise."
    )
    prompt = f"Task: {state.task}\n\nProduce a step-by-step implementation plan:"
    try:
        response = asyncio.run(client.generate(prompt=prompt, system=system))
        plan = [line.strip() for line in response.text.splitlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("planner_node: OllamaClient.generate failed: %s", exc)
        plan = [f"Implement: {state.task}"]
    return {"plan": plan}


def context_retriever_node(state: AgentState) -> dict[str, Any]:
    """Retrieve relevant symbols and wiki entries for the current task.

    Uses ``ContextSelector`` to select the top-K symbols from the
    ``SymbolGraph`` and ``WikiManager.search_entries()`` to find relevant
    wiki entries.

    Args:
        state: Current agent state.  Reads ``state.task`` and ``state.plan``.

    Returns:
        A dict with ``"context_symbols"`` and ``"wiki_context"`` populated.
    """
    config = load_config()
    repo_root = Path.cwd()

    # Load symbol graph from cache if available
    graph = _load_graph(repo_root, config)
    selector = ContextSelector()
    query = state.task + " " + " ".join(state.plan)
    context_symbols = selector.select(query, graph, top_k=config.top_k_context)

    # Search wiki for relevant entries
    wiki_dir = repo_root / config.wiki_dir
    wiki_manager = WikiManager(wiki_dir)
    wiki_context = wiki_manager.search_entries(state.task)

    return {"context_symbols": context_symbols, "wiki_context": wiki_context}


def code_generator_node(state: AgentState) -> dict[str, Any]:
    """Generate a unified diff patch for the current task.

    Builds a prompt from the task, plan, context symbols, wiki entries, and
    (on retries) the previous validation diagnostics.  Calls
    ``OllamaClient.generate()`` and stores the response as ``state.patch``.

    Args:
        state: Current agent state.  Reads ``task``, ``plan``,
            ``context_symbols``, ``wiki_context``, ``validation_result``,
            and ``retry_count``.

    Returns:
        A dict with ``"patch"`` set to the generated diff string and
        ``"retry_count"`` incremented by 1 if this is a retry.
    """
    import asyncio

    client = OllamaClient()
    system = (
        "You are an expert Python engineer. "
        "Produce a unified diff patch (git diff format) that implements the requested change. "
        "Output ONLY the diff — no explanation, no markdown fences."
    )
    prompt = _build_code_gen_prompt(state)
    try:
        response = asyncio.run(client.generate(prompt=prompt, system=system))
        patch = response.text.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("code_generator_node: OllamaClient.generate failed: %s", exc)
        patch = ""

    new_retry_count = (
        state.retry_count + 1 if state.validation_result is not None else state.retry_count
    )
    return {"patch": patch, "retry_count": new_retry_count}


def validator_node(state: AgentState) -> dict[str, Any]:
    """Validate the current patch using ValidationRunner.

    Runs all four validators (pytest, mypy, ruff, contracts) against a
    temporary copy of the repository.  Does NOT apply the patch.

    Args:
        state: Current agent state.  Reads ``state.patch``.

    Returns:
        A dict with ``"validation_result"`` set to the ``ValidationResult``.
    """
    from local_sage.validation.runner import ValidationRunner

    config = load_config()
    repo_root = Path.cwd()
    runner = ValidationRunner(
        repo_root=repo_root,
        manual_review=config.manual_review,
        pytest_timeout=config.pytest_timeout,
        mypy_timeout=config.mypy_timeout,
        ruff_timeout=config.ruff_timeout,
    )
    patch = state.patch or ""
    try:
        result = runner.validate_only(patch)
    except Exception as exc:  # noqa: BLE001
        logger.error("validator_node: ValidationRunner failed: %s", exc)
        from local_sage.validation.result import ValidationFailure, ValidationResult

        result = ValidationResult(
            passed=False,
            failures=[ValidationFailure(tool="validator", message=str(exc))],
            pytest_counts=None,
            mypy_errors=None,
            ruff_violations=None,
            contract_failures=None,
            duration_ms=0,
        )
    return {"validation_result": result}


def memory_writer_node(state: AgentState) -> dict[str, Any]:
    """Persist the completed task to SessionManager and WikiManager.

    Called only after a patch passes validation.  Records the task, patch,
    and result in the SQLite session database and writes a wiki entry
    summarising the change.

    Args:
        state: Current agent state.  Reads ``task``, ``patch``,
            ``validation_result``, and ``session_id``.

    Returns:
        An empty dict (this node only produces side effects).
    """
    config = load_config()
    repo_root = Path.cwd()

    # Persist to session memory
    db_path = repo_root / config.sage_dir / "memory.db"
    if db_path.exists() and state.session_id:
        try:
            session_manager = SessionManager(db_path)
            session_manager.record_task(
                session_id=state.session_id,
                task=state.task,
                patch=state.patch or "",
                result=state.validation_result,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory_writer_node: SessionManager.record_task failed: %s", exc)

    # Write wiki entry
    wiki_dir = repo_root / config.wiki_dir
    wiki_manager = WikiManager(wiki_dir)
    _write_wiki_entry(wiki_manager, state)

    return {}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_graph(repo_root: Path, config: SageConfig) -> SymbolGraph:
    """Load the SymbolGraph from cache, or return an empty graph.

    Args:
        repo_root: Repository root directory.
        config: Loaded SageConfig.

    Returns:
        A ``SymbolGraph`` loaded from ``.sage/index.json``, or an empty one.
    """
    from local_sage.repo_graph.indexer import RepoIndexer

    cache_path = repo_root / config.sage_dir / "index.json"
    indexer = RepoIndexer()
    graph = indexer.load_index(cache_path)
    if graph is None:
        logger.info("No cached index found; using empty SymbolGraph.")
        return SymbolGraph()
    return graph


def _build_code_gen_prompt(state: AgentState) -> str:
    """Build the code-generation prompt from the current agent state.

    Args:
        state: Current agent state.

    Returns:
        A formatted prompt string for the code generator.
    """
    parts: list[str] = [f"Task: {state.task}\n"]
    if state.plan:
        parts.append("Plan:\n" + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(state.plan)))
    if state.context_symbols:
        snippets = "\n\n".join(
            f"# {s.file_path}:{s.start_line}\n{s.source[:500]}" for s in state.context_symbols[:5]
        )
        parts.append(f"\nRelevant code:\n{snippets}")
    if state.wiki_context:
        wiki_text = "\n\n".join(f"## {e.title}\n{e.content[:300]}" for e in state.wiki_context[:3])
        parts.append(f"\nWiki context:\n{wiki_text}")
    if state.validation_result is not None and not state.validation_result.passed:
        parts.append(f"\nPrevious attempt failed:\n{state.validation_result.to_retry_prompt()}")
    parts.append("\nProduce a unified diff patch:")
    return "\n".join(parts)


def _write_wiki_entry(wiki_manager: WikiManager, state: AgentState) -> None:
    """Write a wiki entry summarising the completed task.

    Args:
        wiki_manager: Initialised WikiManager instance.
        state: Current agent state with task and patch information.
    """
    title = f"Task: {state.task[:60]}"
    passed = state.validation_result.passed if state.validation_result else False
    status = "✓ Applied" if passed else "✗ Failed"
    content = f"# {title}\n\n**Status**: {status}\n\n**Task**: {state.task}\n\n"
    if state.plan:
        content += "**Plan**:\n" + "\n".join(f"- {s}" for s in state.plan) + "\n\n"
    if state.patch:
        content += f"**Patch** (first 500 chars):\n```diff\n{state.patch[:500]}\n```\n"
    try:
        wiki_manager.write_entry(title, content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_writer_node: WikiManager.write_entry failed: %s", exc)
