"""Configuration management for local-sage.

Loads ``SageConfig`` from (in priority order):
1. Environment variables prefixed with ``SAGE_`` (highest priority).
2. A ``.env`` file at the repository root (loaded into the environment).
3. A ``sage.toml`` file at the repository root.
4. Dataclass field defaults (lowest priority).

Example ``.env``::

    SAGE_OLLAMA_MODEL=qwen2.5-coder:7b
    SAGE_MAX_RETRIES=5
    SAGE_MYPY_TIMEOUT=300

Example ``sage.toml``::

    ollama_base_url = "http://localhost:11434"
    max_retries = 5
    manual_review = true
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass
class SageConfig:
    """Runtime configuration for the local-sage agent.

    All fields can be overridden via environment variables (``SAGE_<FIELD_NAME>``
    in upper-case) or a ``sage.toml`` file at the repository root.

    Attributes:
        ollama_base_url: Base URL of the Ollama inference server.
        ollama_model: Model identifier to use for code generation.
        ollama_timeout: Maximum seconds to wait for a generation response.
        max_retries: Maximum number of code-generation retries on validation failure.
        pytest_timeout: Subprocess timeout in seconds for pytest runs.
        mypy_timeout: Subprocess timeout in seconds for mypy runs.
        ruff_timeout: Subprocess timeout in seconds for ruff runs.
        top_k_context: Number of symbols to include in the context window.
        wiki_dir: Directory name (relative to repo root) for wiki markdown files.
        sage_dir: Directory name (relative to repo root) for agent state files.
        manual_review: When True, require explicit user confirmation before applying patches.
        embedding_model: HuggingFace sentence-transformers model for semantic memory.
    """

    model_provider: str = "ollama"  # "ollama" | "groq"
    groq_model: str = "llama-3.1-8b-instant"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_timeout: int = 120
    max_retries: int = 3
    pytest_timeout: int = 60
    mypy_timeout: int = 60
    ruff_timeout: int = 30
    top_k_context: int = 10
    wiki_dir: str = "wiki"
    sage_dir: str = ".sage"
    manual_review: bool = False
    embedding_model: str = "multi-qa-MiniLM-L6-cos-v1"


def _load_dotenv(env_path: Path) -> None:
    """Load a ``.env`` file into ``os.environ`` (stdlib only, no dependencies).

    Parses ``KEY=VALUE`` lines, strips quotes, skips comments and blank lines.
    Only sets variables that are **not already set** in the environment, so
    real environment variables always take precedence.

    Args:
        env_path: Path to the ``.env`` file.  Silently ignored if missing.
    """
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        value = raw_value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_toml(toml_path: Path) -> dict[str, Any]:
    """Load a TOML file and return its contents as a dict.

    Args:
        toml_path: Absolute or relative path to the TOML file.

    Returns:
        Parsed TOML contents, or an empty dict if the file does not exist.
    """
    if not toml_path.exists():
        return {}
    with toml_path.open("rb") as fh:
        return tomllib.load(fh)


def _apply_env_overrides(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Override config values with ``SAGE_*`` environment variables.

    Each field ``foo_bar`` maps to the environment variable ``SAGE_FOO_BAR``.
    Values are coerced to the correct Python type based on the dataclass field
    default value type (avoids issues with stringified annotations).

    Args:
        config_dict: Mutable dict of config values to update in-place.

    Returns:
        The updated config dict (same object, mutated).
    """
    # Use the default value to determine the target type — this is robust
    # against PEP 563 stringified annotations (from __future__ import annotations).
    defaults = SageConfig()
    for f in fields(SageConfig):
        env_key = f"SAGE_{f.name.upper()}"
        raw = os.environ.get(env_key)
        if raw is None:
            continue
        default_value = getattr(defaults, f.name)
        config_dict[f.name] = _coerce(raw, type(default_value))
    return config_dict


def _coerce(value: str, target_type: type) -> Any:
    """Coerce a string environment variable value to the target Python type.

    Args:
        value: Raw string value from the environment.
        target_type: The Python type to coerce to (``int``, ``bool``, or ``str``).

    Returns:
        The coerced value.

    Raises:
        ValueError: If the value cannot be coerced to the target type.
    """
    if target_type is bool:
        return value.lower() in {"1", "true", "yes", "on"}
    if target_type is int:
        return int(value)
    return value


def load_config(repo_root: Path | None = None) -> SageConfig:
    """Load ``SageConfig`` from ``sage.toml`` and environment variables.

    Resolution order (highest priority wins):
    1. ``SAGE_*`` environment variables.
    2. ``sage.toml`` at *repo_root* (or the current working directory).
    3. Dataclass field defaults.

    Args:
        repo_root: Root directory of the repository to look for ``sage.toml``.
            Defaults to the current working directory if not provided.

    Returns:
        A fully populated ``SageConfig`` instance.
    """
    root = repo_root if repo_root is not None else Path.cwd()

    # Load .env first (lowest priority — real env vars override it)
    _load_dotenv(root / ".env")

    toml_path = root / "sage.toml"

    config_dict: dict[str, Any] = _load_toml(toml_path)
    _apply_env_overrides(config_dict)

    # Filter to only known fields to avoid unexpected keyword arguments.
    known_fields = {f.name for f in fields(SageConfig)}
    filtered = {k: v for k, v in config_dict.items() if k in known_fields}

    return SageConfig(**filtered)
