# local-sage

## Problem

Small local language models like Qwen2.5 Coder 7B can generate plausible code, but they fail in predictable ways: malformed diffs, wrong exception types, missing edge-case handling, and context drift across multi-file changes. Running a raw model against a repository produces patches that look correct but break tests, type checks, or declared contracts.

local-sage addresses this by wrapping a 7B model in a **validation-gated agent loop** that refuses to apply any patch until it passes pytest, mypy, ruff, and YAML contract checks on a temporary copy of the repository.

## How It Works

local-sage is organised into six layers:

1. **Model (Layer 1)** — `OllamaClient` calls Qwen2.5 Coder 7B via `localhost:11434`. All inference stays on-device.
2. **Orchestration (Layer 2)** — LangGraph nodes (`planner → context_retriever → code_generator → validator → memory_writer`) coordinate the agent loop with retry on validation failure.
3. **Repo Graph (Layer 3)** — tree-sitter parses Python into a NetworkX symbol graph; Personalized PageRank selects the most relevant context for each task.
4. **Session Memory (Layer 4)** — SQLite stores task history, token counts, and observations; Mem0 provides semantic search over past decisions.
5. **Wiki (Layer 5)** — the agent maintains a markdown knowledge base that accumulates insights across tasks.
6. **Validation (Layer 6)** — every patch is pre-checked, applied to a temp copy via `whatthepatch`, and must pass pytest + mypy + ruff + `ContractChecker` before touching real files.

The `ModelOutputParser` (in `local_sage/agent/`) extracts clean unified diffs from raw model output regardless of surrounding prose or code fences.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Start Ollama and pull the model
ollama pull qwen2.5-coder:7b

# Initialise and start the agent
sage start

# Run a coding task
sage task "fix the divide-by-zero bug in simple_api/core.py"

# Run the full benchmark suite
python evals/runner.py

# Run the baseline (raw Ollama, no scaffolding)
python evals/baseline.py
```

## Benchmark Results

| Category | Tasks | Pass Rate (local-sage) | Pass Rate (Baseline) |
|---|---|---|---|
| contract_violation | 5 | TBD | TBD |
| edge_case | 5 | TBD | TBD |
| multi_file | 5 | TBD | TBD |
| context_drift | 5 | TBD | TBD |
| **Overall** | **20** | **TBD** | **TBD** |

## Research Contributions

The novel contribution of local-sage is the **validation gate**: a deterministic, multi-tool check that runs before any patch is applied to the real repository.

- **ContractChecker** — loads YAML contracts from `contracts/` and statically verifies that each symbol's `exception_types` and `return_shape` match the source code via AST walking and `typing.get_type_hints()`.
- **pytest** — functional correctness against the existing test suite.
- **mypy** — static type safety.
- **ruff** — lint and format compliance.

Together, these four validators catch the structural failure modes of small local models without requiring a larger or smarter model. The agent retries with diagnostic feedback until all checks pass or the retry budget is exhausted.

## Acknowledgements

- [Aider](https://aider.chat) for the repomap / Personalized PageRank context selection approach.
- [Ollama](https://ollama.ai) for local model serving.
- [LangGraph](https://langchain-ai.github.io/langgraph/) for agent orchestration.
- [whatthepatch](https://github.com/cscorley/whatthepatch) for pure-Python unified diff application.
