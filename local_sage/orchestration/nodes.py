"""LangGraph node functions for Layer 2 â€” Orchestration.

Each node is a pure function ``(state: AgentState) -> dict[str, Any]``
that returns only the fields it modifies.  LangGraph merges the returned
dict back into the full ``AgentState``.

Node execution order:
    planner â†’ context_retriever â†’ code_generator â†’ validator â†’ memory_writer
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from local_sage.agent.parser import ModelOutputParser
from local_sage.config import SageConfig, load_config
from local_sage.memory.session import SessionManager
from local_sage.model.client import OllamaClient
from local_sage.orchestration.state import AgentState
from local_sage.repo_graph.graph import SymbolGraph
from local_sage.repo_graph.selector import ContextSelector
from local_sage.wiki.manager import WikiManager

logger = logging.getLogger(__name__)

CODE_GENERATOR_SYSTEM_PROMPT: str = (
    "You are an expert Python engineer. "
    "Output ONLY search-replace blocks in this exact format â€” no explanation, "
    "no markdown fences, no other text:\n\n"
    "<<<<<<< SEARCH\n"
    "<exact text copied from the file shown, including indentation>\n"
    "=======\n"
    "<replacement text>\n"
    ">>>>>>> REPLACE\n\n"
    "Rules:\n"
    "- SEARCH text MUST be copied character-for-character from the file content shown.\n"
    "- Include enough context lines (at least 3 before and after the change) "
    "to make the match unique.\n"
    "- Output multiple SEARCH/REPLACE blocks if needed.\n"
    "- Do NOT output unified diffs, line numbers, or @@ markers."
)


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
    """Generate search-replace edit blocks for the current task.

    Builds a prompt with real file content and asks the model to output
    SEARCH/REPLACE blocks.  No line numbers are used â€” the model only needs
    to reproduce text it can see.

    Args:
        state: Current agent state.

    Returns:
        Dict with ``"sr_blocks"`` (list of SearchReplaceBlock) and
        ``"retry_count"`` incremented if this is a retry.
    """
    import asyncio

    from local_sage.agent.parser import ModelOutputParser

    client = OllamaClient()
    prompt = _build_code_gen_prompt(state)
    sr_blocks: list = []
    try:
        response = asyncio.run(
            client.generate(prompt=prompt, system=CODE_GENERATOR_SYSTEM_PROMPT)
        )
        sr_blocks = ModelOutputParser().extract_search_replace_blocks(response.text)
        if not sr_blocks:
            logger.warning("no search-replace blocks found in model output")
    except Exception as exc:  # noqa: BLE001
        logger.warning("code_generator_node: OllamaClient.generate failed: %s", exc)

    patch_str = _build_patch_from_blocks(sr_blocks) if sr_blocks else ""

    new_retry_count = (
        state.retry_count + 1 if state.validation_result is not None else state.retry_count
    )
    return {"sr_blocks": sr_blocks, "patch": patch_str, "retry_count": new_retry_count}


def validator_node(state: AgentState) -> dict[str, Any]:
    """Validate the current search-replace blocks using ValidationRunner.

    Applies blocks to a temporary copy and runs all four validators.
    Does NOT apply to the real repo.

    Args:
        state: Current agent state.  Reads ``state.sr_blocks``.

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
    blocks = state.sr_blocks or []
    try:
        result = runner.validate_search_replace(blocks)
    except Exception as exc:  # noqa: BLE001
        result = _make_validator_failure(exc)
    return {"validation_result": result}


def _make_validator_failure(exc: Exception) -> "ValidationResult":  # type: ignore[name-defined]
    """Build a failed ValidationResult from an unexpected runner exception.

    Args:
        exc: The exception raised by ValidationRunner.

    Returns:
        A ``ValidationResult`` with ``passed=False`` and one failure entry.
    """
    from local_sage.validation.result import ValidationFailure, ValidationResult

    logger.error("validator_node: ValidationRunner failed: %s", exc)
    return ValidationResult(
        passed=False,
        failures=[ValidationFailure(tool="validator", message=str(exc))],
        pytest_counts=None,
        mypy_errors=None,
        ruff_violations=None,
        contract_failures=None,
        duration_ms=0,
    )


def apply_patch_node(state: AgentState) -> dict[str, Any]:
    """Apply the validated search-replace blocks to the real repository.

    Called only after validator_node returns passed=True.

    Args:
        state: Current agent state.  Reads ``state.sr_blocks``.

    Returns:
        An empty dict (side effect only).
    """
    from local_sage.validation.patcher import Patcher
    from local_sage.validation.exceptions import PatchError

    repo_root = Path.cwd()
    blocks = state.sr_blocks or []
    if not blocks:
        logger.warning("apply_patch_node called with no blocks â€” skipping")
        return {}
    patcher = Patcher()
    try:
        patcher.apply_search_replace(repo_root, blocks)
        logger.info("Search-replace blocks applied to repository successfully")
    except PatchError as exc:
        logger.error("apply_patch_node: PatchError â€” %s", exc.message)
    except Exception as exc:  # noqa: BLE001
        logger.error("apply_patch_node: unexpected error applying blocks â€” %s", exc)
    return {}


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

    Includes actual file content for any file path mentioned in the task
    so the model generates diffs with correct context lines.

    Args:
        state: Current agent state.

    Returns:
        A formatted prompt string for the code generator.
    """
    parts: list[str] = [f"Task: {state.task}\n"]
    if state.plan:
        parts.append("Plan:\n" + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(state.plan)))

    # Include full content of any file explicitly mentioned in the task
    file_content_block = _extract_file_content_for_task(state.task)
    if file_content_block:
        parts.append(file_content_block)
    elif state.context_symbols:
        # Fall back to truncated symbol snippets when no explicit file named
        snippets = _build_symbol_snippets(state.context_symbols)
        parts.append(f"\nRelevant code:\n{snippets}")

    if state.wiki_context:
        wiki_text = "\n\n".join(f"## {e.title}\n{e.content[:300]}" for e in state.wiki_context[:3])
        parts.append(f"\nWiki context:\n{wiki_text}")
    if state.validation_result is not None and not state.validation_result.passed:
        parts.append(f"\nPrevious attempt failed:\n{state.validation_result.to_retry_prompt()}")
    parts.append(
        "\nProduce SEARCH/REPLACE blocks. "
        "Context lines MUST be copied exactly from the file content shown above â€” "
        "do not guess or reconstruct lines from memory."
    )
    return "\n".join(parts)


def _extract_file_content_for_task(task: str) -> str:
    """Return a prompt block with actual file content for files named in *task*.

    Scans the task string for Python file paths (``*.py``), reads each file
    from disk relative to ``Path.cwd()``, and returns a formatted block.

    Args:
        task: Natural-language task description.

    Returns:
        Formatted string with file content blocks, or empty string if none found.
    """
    import re

    repo_root = Path.cwd()
    # Match patterns like local_sage/memory/session.py or local_sage\memory\session.py
    pattern = re.compile(r"[\w/\\]+\.py")
    candidate_paths = pattern.findall(task)
    blocks: list[str] = []
    for raw in candidate_paths:
        normalized = Path(raw.replace("\\", "/"))
        full_path = repo_root / normalized
        if full_path.is_file():
            content = full_path.read_text(encoding="utf-8")
            blocks.append(
                f"\nCURRENT CONTENT of {normalized.as_posix()}:\n"
                f"```python\n{content}\n```"
            )
    return "\n".join(blocks)


def _build_symbol_snippets(context_symbols: list) -> str:
    """Build a code snippet block from context symbols.

    Uses the full source for each symbol (no truncation) up to 5 symbols.

    Args:
        context_symbols: List of SymbolInfo objects from the repo graph.

    Returns:
        Formatted string with symbol source blocks.
    """
    return "\n\n".join(
        f"# {s.file_path}:{s.start_line}\n{s.source}" for s in context_symbols[:5]
    )


def _write_wiki_entry(wiki_manager: WikiManager, state: AgentState) -> None:
    """Write a wiki entry summarising the completed task.

    Args:
        wiki_manager: Initialised WikiManager instance.
        state: Current agent state with task and patch information.
    """
    title = f"Task: {state.task[:60]}"
    passed = state.validation_result.passed if state.validation_result else False
    status = "âœ“ Applied" if passed else "âœ— Failed"
    content = f"# {title}\n\n**Status**: {status}\n\n**Task**: {state.task}\n\n"
    if state.plan:
        content += "**Plan**:\n" + "\n".join(f"- {s}" for s in state.plan) + "\n\n"
    if state.patch:
        content += f"**Patch** (first 500 chars):\n```diff\n{state.patch[:500]}\n```\n"
    try:
        wiki_manager.write_entry(title, content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_writer_node: WikiManager.write_entry failed: %s", exc)


def _build_patch_from_blocks(sr_blocks: list) -> str:
    import difflib
    repo_root = Path.cwd()
    patch_str = ""
    for block in sr_blocks:
        search_text = block.search
        replace_text = block.replace
        matches = [
            f for f in repo_root.rglob("*.py")
            if search_text in f.read_text(encoding="utf-8")
        ]
        if len(matches) == 1:
            target = matches[0]
            original_text = target.read_text(encoding="utf-8")
            new_text = original_text.replace(search_text, replace_text, 1)
            original_lines = original_text.splitlines(keepends=True)
            new_lines = new_text.splitlines(keepends=True)
            rel_path = target.relative_to(repo_root).as_posix()
            diff = list(difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}"
            ))
            patch_str += "".join(diff)
    return patch_str
