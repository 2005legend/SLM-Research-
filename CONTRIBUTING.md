# Contributing to local-sage

Thank you for your interest in contributing. This document covers the development setup, coding standards, and contribution workflow.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- [Ollama](https://ollama.ai) with `qwen2.5-coder:7b-instruct-q4_K_M` pulled
- Git

### Install from source

```bash
git clone https://github.com/your-org/local-sage
cd local-sage
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

### Pull the model

```bash
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
```

## Running Tests

```bash
# Unit and property-based tests (no Ollama required)
pytest

# With coverage report
pytest --cov=local_sage --cov-report=term-missing

# Integration tests (requires Ollama + SAGE_INTEGRATION=true)
SAGE_INTEGRATION=true pytest tests/integration/ -v
```

## Code Quality

All code must pass these checks before a PR is merged:

```bash
# Type checking (strict mode)
mypy local_sage/

# Linting
ruff check .

# Formatting
ruff format .
```

## Coding Standards

These are enforced by the test suite (`tests/test_code_quality.py`):

| Standard | Rule |
|---|---|
| Type hints | Every public function parameter and return value must be annotated |
| Docstrings | Every public class and method must have a Google-style docstring |
| File I/O | All paths must use `pathlib.Path` — never raw strings |
| Function length | Maximum 40 lines per function — split if longer |
| Exceptions | All custom exceptions must subclass a domain-specific base (e.g. `OllamaError`, `ValidationError`) |

## Architecture

local-sage is organized into six discrete layers. **No layer may import from a layer above it.**

```
local_sage/
├── model/          # Layer 1 — Ollama async HTTP client
├── orchestration/  # Layer 2 — LangGraph agent loop
├── repo_graph/     # Layer 3 — tree-sitter parser + NetworkX symbol graph
├── memory/         # Layer 4 — SQLite session memory + Mem0 semantic search
├── wiki/           # Layer 5 — markdown knowledge base
└── validation/     # Layer 6 — validation gate (CORE — requires manual review)
```

## Validation Layer — Special Rules

The validation layer (`local_sage/validation/`) is the core novel contribution of this project.

- **No implementation task in this layer should be marked complete without a human reviewing the generated code.**
- The `ContractChecker` in particular must be reviewed before acceptance.
- The `Patcher` must use `whatthepatch` — never the system `patch` utility.

## Mem0 Configuration — Critical Constraint

Mem0 **must** be configured with `embedder.provider = "huggingface"` at all times. It must **never** fall back to OpenAI, Cohere, or any other cloud embedding provider.

The `MEM0_CONFIG` dict in `local_sage/memory/semantic.py` is the single source of truth. Any change that introduces a non-local provider is a breaking change and will be rejected.

See [Mem0 Configuration](#mem0-configuration) in the README for details.

## Pull Request Checklist

Before opening a PR:

- [ ] All tests pass: `pytest`
- [ ] No mypy errors: `mypy local_sage/`
- [ ] No ruff violations: `ruff check . && ruff format --check .`
- [ ] New public functions have type hints and docstrings
- [ ] New file I/O uses `pathlib.Path`
- [ ] Validation layer changes have been manually reviewed
- [ ] Mem0 config still uses `embedder.provider = "huggingface"`

## Project Layout

```
local-sage/
├── local_sage/         # Main package
├── tests/              # Test suite (mirrors local_sage/ structure)
├── contracts/          # YAML contract files for ContractChecker
├── evals/              # Benchmark suite
├── pyproject.toml      # Project metadata and dependencies
├── README.md
└── CONTRIBUTING.md     # This file
```
