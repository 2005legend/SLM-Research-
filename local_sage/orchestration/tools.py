"""LangGraph tool definitions for Layer 2 — Orchestration.

Provides ``@tool``-decorated functions that the agent can call as part of
its reasoning loop.  Each tool is a thin wrapper around the appropriate
layer's public API.
"""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.tools import tool

from local_sage.config import load_config

logger = logging.getLogger(__name__)


@tool
def read_file(path: str) -> str:
    """Read a file from the repository and return its contents.

    Args:
        path: Relative path to the file within the repository root
            (e.g. ``"local_sage/model/client.py"``).

    Returns:
        The full text content of the file, or an error message string if
        the file cannot be read.
    """
    file_path = Path.cwd() / path
    try:
        return file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("read_file tool: cannot read %s: %s", file_path, exc)
        return f"Error reading {path}: {exc}"


@tool
def write_wiki(title: str, content: str) -> None:
    """Write or update a wiki entry in the agent's knowledge base.

    Creates the wiki directory if it does not exist.  Overwrites any
    existing entry with the same title.

    Args:
        title: Human-readable title for the wiki entry.
        content: Full markdown content to write.
    """
    from local_sage.wiki.manager import WikiManager

    config = load_config()
    wiki_dir = Path.cwd() / config.wiki_dir
    manager = WikiManager(wiki_dir)
    try:
        manager.write_entry(title, content)
        logger.info("write_wiki tool: wrote entry '%s'", title)
    except Exception as exc:  # noqa: BLE001
        logger.warning("write_wiki tool: failed to write '%s': %s", title, exc)


@tool
def run_tests(test_path: str | None = None) -> str:
    """Run pytest on the repository or a specific path and return a summary.

    Args:
        test_path: Optional relative path to a specific test file or
            directory.  If ``None``, runs the full test suite.

    Returns:
        A human-readable summary string with pass/fail/error counts, or
        an error message if pytest could not be run.
    """
    from local_sage.validation.pytest_runner import PytestRunner

    config = load_config()
    repo_root = Path.cwd()
    runner = PytestRunner()
    try:
        counts = runner.run(repo_root, timeout=config.pytest_timeout)
        return f"pytest: {counts.passed} passed, {counts.failed} failed, {counts.errors} errors"
    except Exception as exc:  # noqa: BLE001
        logger.warning("run_tests tool: pytest failed: %s", exc)
        return f"Error running tests: {exc}"
