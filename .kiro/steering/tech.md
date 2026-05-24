# Tech Stack

## Runtime
- Python 3.11+
- Ollama — local inference server, OpenAI-compatible API at `localhost:11434`
- Qwen2.5 Coder 7B — primary model (no other models, no external APIs)

## Core Libraries
| Library | Role |
|---|---|
| LangGraph | Agent orchestration loop |
| Tree-sitter | Repo parsing and symbol indexing |
| NetworkX | Call graph and import graph |
| SQLite (stdlib) | Session memory persistence |
| Rich | Terminal UI |

## Validation Tools
| Tool | Role |
|---|---|
| pytest | Test runner |
| mypy | Static type checking |
| ruff | Linting and formatting |

## Common Commands

```bash
# Run tests
pytest

# Type check
mypy .

# Lint / format
ruff check .
ruff format .

# Start the agent
sage start
```

## Dependency Notes
- All file I/O must use `pathlib.Path` — never raw strings
- No pip packages that make outbound network calls at runtime
- Keep dependencies minimal; each layer owns its own imports

## Critical Constraints

### Mem0 — Never use cloud providers
Mem0 MUST be configured with `embedder.provider = "huggingface"` and `sentence-transformers` at all times.
It MUST NOT fall back to OpenAI, Cohere, or any other cloud embedding provider. The `MEM0_CONFIG` in
`local_sage/memory/semantic.py` is the single source of truth for this configuration. Any change to this
config that introduces a non-local provider is a breaking change.

### Validation layer — Manual review required
The validation layer (`local_sage/validation/`) is the core novel contribution of this project. No
implementation task in this layer should be marked complete without a human reviewing the generated code.
The ContractChecker in particular must be reviewed before acceptance.

### Patcher — Use whatthepatch, not system patch
`Patcher.apply_to_temp()` MUST use the `whatthepatch` library for diff application. Do NOT use the system
`patch -p1` utility — it is not available on Windows and not guaranteed on all Linux distros.

### LangGraph version
Use `langgraph>=0.3,<0.4`. Do not use 0.2.x — it is outdated.
