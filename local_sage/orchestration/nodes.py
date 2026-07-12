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
from local_sage.model.client import OllamaClient, get_client_sync
from local_sage.orchestration.state import AgentState
from local_sage.repo_graph.graph import SymbolGraph
from local_sage.repo_graph.selector import ContextSelector
from local_sage.wiki.manager import WikiManager

logger = logging.getLogger(__name__)

CODE_GENERATOR_SYSTEM_PROMPT: str = (
    "You are an expert Python engineer.\n"
    "CRITICAL FORMAT RULES:\n"
    "- Output ONLY search-replace blocks, nothing else\n"
    "- SEARCH text must be copied EXACTLY from the file shown\n"
    "- REPLACE text must be the complete replacement\n"
    "- Do not output explanations before or after blocks\n"
    "- Do not output partial blocks\n"
    "- If you cannot fit the change in one block, use multiple blocks\n"
    "- Each block must be complete \u2014 never truncate mid-block\n\n"
    "<<<<<<< SEARCH\n"
    "[exact text to find]\n"
    "=======\n"
    "[replacement text]\n"
    ">>>>>>> REPLACE"
)

API_CODE_GENERATOR_SYSTEM_PROMPT: str = (
    "You are an expert Python engineer. "
    "Output the FULL rewritten content of the target file inside a single standard ```python code block. "
    "Do NOT use search/replace blocks or diffs. Include the ENTIRE file content with your changes applied."
)

# Injected as a prefix on every retry (attempt 2+) to counteract the format
# drift that models exhibit after a first failure or timeout.
RETRY_FORMAT_REMINDER: str = (
    "Output ONLY a SEARCH/REPLACE block. "
    "Do NOT use markdown code fences (no ```python). "
    "Do NOT include any explanation text before or after the block."
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

    if state.task.startswith("Goal:"):
        return {"plan": []}

    load_config()
    client = get_client_sync()
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
    logger.warning(
        "DEBUG: graph nodes=%d, query=%r, found=%d symbols: %s",
        graph._graph.number_of_nodes(),
        query[:80],
        len(context_symbols),
        [s.file_path for s in context_symbols],
    )

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

    client = get_client_sync()
    sr_blocks = _execute_code_generation(state, client)
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
    import re
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
    
    target_file = None
    task_files = re.findall(r"[\w/\\]+\.py\b", state.task)
    if task_files:
        target_file = task_files[0]
        
    try:
        result = runner.validate_search_replace(blocks, target_file=target_file)
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
        confidence_score=0,
    )


def apply_patch_node(state: AgentState) -> dict[str, Any]:
    """Apply the validated search-replace blocks to the real repository.

    Called only after validator_node returns passed=True.

    Args:
        state: Current agent state.  Reads ``state.sr_blocks``.

    Returns:
        An empty dict (side effect only).
    """
    import re
    from local_sage.validation.patcher import Patcher
    from local_sage.validation.exceptions import PatchError

    repo_root = Path.cwd()
    blocks = state.sr_blocks or []
    if not blocks:
        logger.warning("apply_patch_node called with no blocks — skipping")
        return {}
        
    target_file = None
    task_files = re.findall(r"[\w/\\]+\.py\b", state.task)
    if task_files:
        target_file = task_files[0]
        
    patcher = Patcher()
    try:
        patcher.apply_search_replace(repo_root, blocks, target_file=target_file)
        logger.info("Search-replace blocks applied to repository successfully")
    except PatchError as exc:
        logger.error("apply_patch_node: PatchError — %s", exc.message)
    except Exception as exc:  # noqa: BLE001
        logger.error("apply_patch_node: unexpected error applying blocks — %s", exc)
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
    """Load the SymbolGraph from cache, or build it if missing/stale.

    Args:
        repo_root: Repository root directory.
        config: Loaded SageConfig.

    Returns:
        A ``SymbolGraph`` instance.
    """
    from local_sage.repo_graph.indexer import RepoIndexer

    cache_path = repo_root / config.sage_dir / "index.json"
    indexer = RepoIndexer()
    graph = indexer.load_index(cache_path)
    if not graph:
        logger.info("Index is stale or missing, rebuilding...")
        graph = indexer.index_repo(repo_root)
        indexer.save_index(graph, cache_path)
    return graph


def _build_local_code_gen_prompt(state: AgentState) -> str:
    """Build the code-generation prompt from the current agent state.

    Includes actual file content for any file path mentioned in the task
    so the model generates diffs with correct context lines.

    Uses windowed context for better token efficiency when context_symbols
    are available.  If the task names a .py file that is not among the
    retrieved context symbols (e.g. a newly created temp file that was not
    in the stale index), the file is read directly from disk and injected
    so the model always sees the target file content.

    On retries the validation failure section is capped at 800 chars to
    prevent prompt blowup caused by large ruff/mypy outputs.

    Args:
        state: Current agent state.

    Returns:
        A formatted prompt string for the code generator.
    """
    import re
    from local_sage.agent.context import get_windowed_context

    repo_root = Path.cwd()
    parts: list[str] = [f"Task: {state.task}\n"]
    if state.plan:
        parts.append("Plan:\n" + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(state.plan)))

    # --- Context: windowed symbol context OR direct file injection ---
    target_file_shown = False
    
    context_symbols = state.context_symbols
    if context_symbols and not _task_file_matches_symbol(state.task, context_symbols[0]):
        logger.warning(
            "_build_local_code_gen_prompt: top symbol %s does not match task file, clearing stale context",
            getattr(context_symbols[0], 'file_path', 'unknown')
        )
        context_symbols = []

    if context_symbols:
        # Use the first (most relevant) symbol for windowed context
        target_symbol = context_symbols[0]
        windowed = get_windowed_context(target_symbol, repo_root, context_lines=20)
        if windowed:
            parts.append(
                f"\nTARGET FILE: {target_symbol.file_path}\n"
                f"```python\n{windowed}\n```"
            )
            target_file_shown = True
            logger.debug(
                "_build_local_code_gen_prompt: using windowed context for "
                "%s, %d lines",
                target_symbol.file_path,
                len(windowed.splitlines()),
            )
        else:
            # Fall back to symbol snippets if windowed context fails
            snippets = _build_symbol_snippets(context_symbols)
            parts.append(f"\nRelevant code:\n{snippets}")
            target_file_shown = True

    # Direct file fallback: if the task explicitly names a .py file that is
    # not reflected in the retrieved symbols, inject the file content directly.
    # This handles newly-created files absent from a stale graph index.
    if not target_file_shown:
        file_content_block = _extract_file_content_for_task(state.task)
        if file_content_block:
            parts.append(file_content_block)
            target_file_shown = True

    # If still not shown, try simple direct read
    if not target_file_shown:
        py_match = re.search(r"([\w/\\]+\.py)", state.task)
        if py_match:
            candidate = repo_root / py_match.group(1).replace("\\", "/")
            if candidate.is_file():
                content = candidate.read_text(encoding="utf-8")
                rel = candidate.relative_to(repo_root).as_posix()
                if len(content) > 3000:
                    content = content[:3000] + "\n... [TRUNCATED]"
                parts.append(f"\nTARGET FILE: {rel}\n```python\n{content}\n```")
                target_file_shown = True
                logger.debug(
                    "_build_local_code_gen_prompt: direct-inject fallback for %s", rel
                )
    
    if not target_file_shown:
         logger.warning("_build_local_code_gen_prompt: could not find/inject any target file content!")

    # --- Wiki context (top 3 entries, 300 chars each) ---
    if state.wiki_context:
        wiki_text = "\n\n".join(f"## {e.title}\n{e.content[:300]}" for e in state.wiki_context[:3])
        parts.append(f"\nWiki context:\n{wiki_text}")

    # --- Retry feedback (capped at 800 chars to prevent prompt blowup) ---
    if state.validation_result is not None and not state.validation_result.passed:
        retry_text = state.validation_result.to_retry_prompt()
        if len(retry_text) > 800:
            retry_text = retry_text[:800] + "\n... [truncated — focus on the first error]"
        parts.append(f"\nPrevious attempt failed:\n{retry_text}")

    parts.append(
        "\nProduce SEARCH/REPLACE blocks. "
        "Context lines MUST be copied exactly from the file content shown above — "
        "do not guess or reconstruct lines from memory."
    )
    return "\n".join(parts)


def _task_file_matches_symbol(task: str, symbol: Any) -> bool:
    """Return True if the .py filename in *task* matches *symbol*'s file path.

    Used to detect when the top retrieved symbol is from a different file than
    the one explicitly named in the task string (stale-index mismatch).

    Args:
        task: Natural-language task string that may contain a .py path.
        symbol: A ``SymbolInfo`` object with a ``file_path`` attribute.

    Returns:
        ``True`` if the task's named file appears in the symbol's file path.
    """
    import re
    from pathlib import Path
    task_files = re.findall(r"[\w/\\]+\.py\b", task)
    if not task_files:
        return True  # no explicit file in task — assume match
        
    symbol_path = str(getattr(symbol, "file_path", "") or "")
    if not symbol_path:
        return False
        
    symbol_name = Path(symbol_path).name
    return any(Path(f).name == symbol_name for f in task_files)


def _extract_file_content_for_task(task: str, use_windowed: bool = False) -> str:
    """Return a prompt block with actual file content for files named in *task*.

    Scans the task string for Python file paths (``*.py``), reads each file
    from disk relative to ``Path.cwd()``, and returns a formatted block.
    
    When use_windowed is True and context_symbols is available, uses windowed
    context instead of full file content to stay within token limits.

    Args:
        task: Natural-language task description.
        use_windowed: If True, prefer windowed context for better token efficiency.

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
            # Truncate to ~3000 chars (approx 750 tokens) to leave room for rest of prompt
            max_chars = 3000
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... [TRUNCATED DUE TO CONTEXT LIMIT]"
            blocks.append(
                f"\nCURRENT CONTENT of {normalized.as_posix()}:\n"
                f"```python\n{content}\n```"
            )
    return "\n".join(blocks)


def _build_symbol_snippets(context_symbols: list[Any]) -> str:
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


def _build_patch_from_blocks(sr_blocks: list[Any]) -> str:
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
                original_lines, new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                n=3
            ))
            patch_str += "".join(diff) + "\n"
    return patch_str


def _get_target_file_content(state: AgentState) -> str | None:
    if not state.context_symbols:
        return None
    target_symbol = state.context_symbols[0]
    repo_root = Path.cwd()
    file_path = repo_root / target_symbol.file_path
    if file_path.exists():
        content = file_path.read_text(encoding="utf-8")
        if len(content) > 12000:
            content = content[:12000] + "\n... [TRUNCATED DUE TO CONTEXT LIMIT]"
        return content
    return None


def _build_api_code_gen_prompt(state: AgentState) -> str:
    """Build the code-generation prompt for an API model (full file replacement)."""
    parts: list[str] = [f"Task: {state.task}\n"]
    if state.plan:
        plan_str = "Plan:\n" + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(state.plan))
        parts.append(plan_str)
        
    if state.wiki_context:
        wiki_text = "\n\n".join(f"## {e.title}\n{e.content[:300]}" for e in state.wiki_context[:3])
        parts.append(f"\nWiki context:\n{wiki_text}")
        
    if state.validation_result is not None and not state.validation_result.passed:
        parts.append(f"\nPrevious attempt failed:\n{state.validation_result.to_retry_prompt()}")
        
    original_content = _get_target_file_content(state)
    if original_content:
        parts.append(f"\nTarget file content:\n```python\n{original_content}\n```")
        
    parts.append(
        "\nOutput the FULL rewritten content of the target file inside a single ```python code block."
    )
    return "\n".join(parts)


def _execute_code_generation(state: AgentState, client: Any) -> list[Any]:
    import asyncio
    from local_sage.agent.parser import ModelOutputParser

    prompt = _build_local_code_gen_prompt(state)
    system_prompt = CODE_GENERATOR_SYSTEM_PROMPT

    # On retry attempts (retry_count >= 1) prepend RETRY_FORMAT_REMINDER to
    # the system prompt.  Format drift is observed specifically after the first
    # failure/timeout, not on the initial call.
    is_retry = state.retry_count >= 1
    if is_retry:
        system_prompt = RETRY_FORMAT_REMINDER + "\n\n" + system_prompt
        logger.warning(
            "code_generator_node: retry attempt %d — prepending RETRY_FORMAT_REMINDER",
            state.retry_count,
        )

    # Calculate prompt stats for debugging
    prompt_chars = len(prompt) + len(system_prompt)
    est_tokens = prompt_chars // 4
    logger.warning(
        f"code_generator_node: prompt length={prompt_chars} chars, "
        f"estimated {est_tokens} tokens"
    )

    # Log context details
    if state.context_symbols:
        logger.warning(
            f"code_generator_node: using {len(state.context_symbols)} context symbols"
        )

    # Check if prompt exceeds reasonable limit for small models
    if est_tokens > 4000:
        logger.warning(
            f"code_generator_node: Prompt token count ({est_tokens}) exceeds 4000. "
            "Consider reducing context size."
        )

    sr_blocks: list[Any] = []
    try:
        response = asyncio.run(client.generate(prompt=prompt, system=system_prompt))
        sr_blocks = ModelOutputParser().extract_search_replace_blocks(response.text)

        if not sr_blocks:
            logger.warning("no search-replace blocks found in model output. Raw output:\n%s", response.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("code_generator_node: generate failed: %s", exc)

    return sr_blocks
