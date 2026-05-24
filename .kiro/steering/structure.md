# Project Structure

## Layer Architecture

local-sage is organized into six discrete layers. Each layer lives in its own package. Do not merge layers or import across them in ways that create circular dependencies.

```
local_sage/
├── model/          # Layer 1 — Ollama client wrapper
├── orchestration/  # Layer 2 — LangGraph agent loop
├── repo_graph/     # Layer 3 — tree-sitter parser, symbol index, import/call graphs
├── memory/         # Layer 4 — SQLite session memory schema and queries
├── wiki/           # Layer 5 — markdown knowledge base (model-writable)
└── validation/     # Layer 6 — contract checker, test/lint/type runner (CORE)
```

## Top-Level Layout

```
local-sage/
├── local_sage/         # Main package (six layers above)
├── tests/              # Mirror of local_sage/ — one test file per module
│   ├── model/
│   ├── orchestration/
│   ├── repo_graph/
│   ├── memory/
│   ├── wiki/
│   └── validation/
├── .kiro/              # Kiro steering and specs
├── pyproject.toml      # Project metadata, dependencies, tool config
└── README.md
```

## Conventions

- Every module in `local_sage/` has a corresponding test file under `tests/`
- Test files mirror the source path: `local_sage/model/client.py` → `tests/model/test_client.py`
- Each layer package exposes a clean public API via its `__init__.py`; internals are prefixed with `_`
- Entry point is defined in `pyproject.toml` as `sage = "local_sage.__main__:main"`

## Coding Standards

- Type hints on every function signature — no exceptions
- Docstrings on every public class and method (Google style)
- Max function length: 40 lines — split if longer
- All file paths use `pathlib.Path`, never raw strings
- Typed exceptions only — no bare `except Exception` catches
- Validation layer (`local_sage/validation/`) requires manual review before accepting generated code
