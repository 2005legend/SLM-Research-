"""local-sage: A repo-aware, validation-gated coding agent.

Wraps Qwen2.5 Coder 7B (served by Ollama) with structural understanding of a
Python codebase, persistent session memory, an agent-maintained wiki, and a
deterministic validation gate (pytest + mypy + ruff + contract checker).

All operations run entirely locally — no outbound network calls except to
``localhost:11434``.
"""

__version__ = "0.1.0"
