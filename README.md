# local-sage

A repo-aware, validation-gated coding agent that makes **Qwen2.5 Coder 7B** production-reliable on
consumer hardware (RTX 3060 / 8 GB VRAM).

## Core Thesis

Small local models fail in predictable, structural ways. local-sage catches those failures
*deterministically* via a validation gate (pytest + mypy + ruff + contract checker) instead of relying on
a bigger or smarter model.

## Features

- **Repo graph** — tree-sitter parses your Python codebase into a NetworkX symbol graph; Personalized
  PageRank selects the most relevant context for each task (inspired by
  [Aider's repomap](https://aider.chat/2023/10/22/repomap.html)).
- **Validation gate** — every generated patch is applied to a temp copy of the repo and must pass pytest,
  mypy, ruff, and contract checks before touching real files.
- **Session memory** — SQLite stores task history; Mem0 with local sentence-transformers embeddings
  provides semantic search over past observations.
- **Agent wiki** — the agent maintains a markdown knowledge base that accumulates insights across tasks.
- **Fully local** — zero outbound network calls except to `localhost:11434` (Ollama).

## Hardware Requirements

| Component | Minimum |
|---|---|
| GPU | RTX 3060 or equivalent, 8 GB VRAM |
| RAM | 16 GB system RAM |
| Storage | ~10 GB (model + index) |

## Installation

```bash
pip install local-sage
```

Or install from source:

```bash
git clone https://github.com/your-org/local-sage
cd local-sage
pip install -e ".[dev]"
```

## Prerequisites

1. **Ollama** — install from [ollama.ai](https://ollama.ai) and pull the model:

   ```bash
   ollama pull qwen2.5-coder:7b-instruct-q4_K_M
   ```

2. **Python 3.11+**

## Quick Start

```bash
# Boot the agent, index the repo, load the latest session
sage start

# Run a coding task
sage task "add input validation to the /users POST endpoint"

# Validate a patch without applying it
sage validate --patch my_changes.patch

# Check agent and system status
sage status
```

## All Commands

| Command | Description |
|---|---|
| `sage start` | Boot the agent, index the repo, load the latest session |
| `sage task "<description>"` | Run a coding task through the full agent loop |
| `sage validate --patch <path>` | Validate a patch file without applying it |
| `sage benchmark --suite <path>` | Run the eval benchmark suite |
| `sage memory show` | Display current session memory in a Rich table |
| `sage wiki list` | List all wiki entries with timestamps |
| `sage wiki show <entry>` | Display the full content of a wiki entry |
| `sage status` | Show Ollama model status, repo index stats, and session info |

## Configuration

local-sage can be configured via environment variables or a `sage.toml` file at the repo root.

### `sage.toml` example

```toml
ollama_base_url = "http://localhost:11434"
ollama_model = "qwen2.5-coder:7b-instruct-q4_K_M"
ollama_timeout = 120
max_retries = 3
pytest_timeout = 60
mypy_timeout = 60
ruff_timeout = 30
top_k_context = 10
wiki_dir = "wiki"
sage_dir = ".sage"
manual_review = false
embedding_model = "multi-qa-MiniLM-L6-cos-v1"
```

### Environment variables

Each field maps to a `SAGE_` prefixed environment variable, e.g.:

```bash
export SAGE_OLLAMA_BASE_URL="http://localhost:11434"
export SAGE_MAX_RETRIES=5
export SAGE_MANUAL_REVIEW=true
```

## Architecture

```
local_sage/
├── model/          # Layer 1 — Ollama async HTTP client
├── orchestration/  # Layer 2 — LangGraph agent loop
├── repo_graph/     # Layer 3 — tree-sitter parser + NetworkX symbol graph
├── memory/         # Layer 4 — SQLite session memory + Mem0 semantic search
├── wiki/           # Layer 5 — markdown knowledge base
└── validation/     # Layer 6 — validation gate (pytest + mypy + ruff + contracts)
```

Data flows top-down during task execution and bottom-up during context retrieval. No layer imports from a
layer above it.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy local_sage/

# Lint and format
ruff check .
ruff format .

# Run tests with coverage
pytest --cov=local_sage --cov-report=term-missing
```

## Runtime Files

local-sage creates the following files in your repository:

```
<repo_root>/
├── .sage/
│   ├── index.json    ← SymbolGraph cache
│   ├── memory.db     ← SQLite session database
│   └── vectors/      ← Qdrant on-disk vector store
├── wiki/             ← Agent-maintained markdown knowledge base
└── contracts/        ← YAML contract files (optional)
```

Add `.sage/` to your `.gitignore` if you don't want to commit the index and memory database.

## Mem0 Configuration

local-sage uses [Mem0](https://github.com/mem0ai/mem0) for semantic memory search over past observations. It is configured to run **entirely locally** — no cloud API keys are required or used.

### Critical constraint: always use HuggingFace embedder

Mem0 **must** use `embedder.provider = "huggingface"` with `sentence-transformers`. It must **never** fall back to OpenAI, Cohere, or any other cloud embedding provider.

The configuration in `local_sage/memory/semantic.py`:

```python
MEM0_CONFIG = {
    "embedder": {
        "provider": "huggingface",          # ← NEVER change this to "openai"
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
        "config": {"collection_name": "local_sage", "path": ".sage/vectors"},
    },
}
```

The `multi-qa-MiniLM-L6-cos-v1` model produces 384-dimensional embeddings and fits in ~90 MB RAM. The vector store uses Qdrant in local on-disk mode — no Qdrant server is required.

Any change to this configuration that introduces a non-local provider is a **breaking change** and will be rejected in code review.

## Inspiration and References

- [Aider repomap](https://aider.chat/2023/10/22/repomap.html) — Personalized PageRank for context selection
- [SWE-bench](https://arxiv.org/abs/2310.06770) — Evaluation methodology
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) — Validation and sandboxing approach
- [Agentless](https://github.com/OpenAutoCoder/Agentless) — Minimal agent baseline
- [Karpathy on agent knowledge bases](https://x.com/karpathy)
- [Hermes function-calling pattern](https://github.com/NousResearch/hermes-function-calling)

## License

MIT
