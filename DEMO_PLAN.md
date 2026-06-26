# Local-Sage Full CLI Demonstration Plan

## What I Was Attempting

I was creating a comprehensive demonstration script to show all working components of the local-sage tool without needing the CLI (since there's a Typer compatibility issue).

## Changes Attempted

### ✗ File: `demo_working.py` (CORRUPTED - please delete)
This file has syntax errors from incomplete edits. Should be discarded.

### ✓ What This Demo Should Show

The demo should demonstrate all 12 major components working:

```
[1] CONFIG LOADING
    - Load SageConfig from sage.toml or defaults
    - Display: ollama_model, max_retries, timeouts, directories

[2] REPOSITORY INDEXING  
    - Use RepoIndexer to parse Python code into symbol graph
    - Display: node count (1183 symbols), edge count (351 relationships)

[3] SESSION MANAGEMENT
    - Create/load SessionManager with SQLite backend
    - Display: session_id, task_count, token counts, costs

[4] MODEL CLIENT (Ollama)
    - Initialize OllamaClient
    - Check Ollama health (online/offline)
    - Model: qwen2.5-coder:7b at localhost:11434

[5] AGENT OUTPUT PARSER
    - Parse raw model output with code fences
    - Extract unified diff using ModelOutputParser.extract_diff()
    - Handle model prose + markdown formatting

[6] VALIDATION - PATCHER
    - Initialize Patcher for applying patches
    - Key methods: apply_to_temp(), apply_to_repo(), revert()

[7] VALIDATION - CONTRACT CHECKER
    - Load YAML contracts from contracts/ directory
    - Initialize ContractChecker
    - Method: check(repo_dir) returns list[ContractFailure]

[8] VALIDATION RUNNERS
    - PytestRunner() - functional correctness
    - MypyRunner() - static type checking
    - RuffRunner() - lint and format compliance
    - All use: run(repo_dir, timeout) pattern

[9] VALIDATION RUNNER (Integration)
    - ValidationRunner combines all 4 validators
    - Pre-checks patches on temporary copies
    - Refuses to apply until all checks pass

[10] WIKI MANAGER
     - WikiManager for markdown knowledge base
     - list_entries(), read_entry(title)

[11] AGENT STATE & ORCHESTRATION
     - AgentState dataclass with task, max_retries, session_id
     - LangGraph with 5 nodes: planner → context_retriever → code_generator → validator → memory_writer

[12] SEMANTIC MEMORY
     - SemanticMemory for storing observations
     - Uses sentence-transformers embeddings
     - Qdrant vector database
```

## Test Results So Far

### ✓ Passing Tests
```
345 passed, 6 skipped in 45.53s
```
All critical tests are passing.

### ✓ Working Components (Verified)
1. Config loading
2. Repository indexing (1183 symbols indexed)
3. Session management (new session created)
4. Validation runner (integrated successfully)
5. Wiki manager (initialized)
6. Agent orchestration (LangGraph built)

### ⚠ Dependencies Not Met
- **Ollama Server**: Not running (curl to localhost:11434 failed)
  - Need to start: `ollama serve`
  - Need to pull: `ollama pull qwen2.5-coder:7b`

## Next Steps

1. **Start Ollama**: `ollama serve` (in separate terminal)
2. **Create Clean Demo**: A new Python script that shows all 12 components
3. **Run Full Agent Loop**: Once Ollama is running

## Files to Create

- `demo_clean.py` - Clean demonstration with no syntax errors
- `OLLAMA_SETUP.md` - Step-by-step Ollama startup guide

## Commands Summary

```bash
# Area 1: Automated Tests (No Ollama needed)
pytest                              # Run all tests
pytest -v                          # Verbose output
pytest --cov=local_sage            # With coverage

# Area 2: Static Checks
mypy .                             # Type checking
ruff check .                       # Linting
ruff format --check .              # Format check

# Area 3: Start Agent (Requires Ollama)
ollama serve                       # Terminal 1: Start Ollama
ollama pull qwen2.5-coder:7b      # Terminal 2: Pull model
python demo_clean.py               # Terminal 3: Run demo

# Full Agent Loop
sage start                         # Initialize (when CLI fixed)
sage task "Your task description"  # Run coding task
sage status                        # Check status
sage memory show                   # View session info
sage wiki list                     # Show wiki entries
```

## Architecture Layers

```
Layer 0: CLI (Typer) - commands: start, task, validate, status, memory, wiki
Layer 1: Model (OllamaClient) - inference at localhost:11434
Layer 2: Orchestration (LangGraph) - agent loop with retry logic
Layer 3: Repo Graph (NetworkX) - symbol parsing & context selection
Layer 4: Session Memory (SQLite) - task history & semantic search
Layer 5: Wiki (Markdown) - knowledge base accumulation
Layer 6: Validation (4-tool gate) - pytest, mypy, ruff, contracts
```

## What the Tool Does

**Input**: A coding task description (e.g., "fix the divide-by-zero bug in app.py")

**Process**:
1. Parse task with Planner node
2. Retrieve relevant code context using Repo Graph
3. Generate code with Qwen2.5-Coder 7B
4. Parse unified diff from model output
5. Pre-check patch on temporary copy:
   - Run pytest (functional correctness)
   - Run mypy (type safety)
   - Run ruff (lint/format)
   - Check YAML contracts
6. If all pass → apply to real repo. If fail → retry with diagnostics.

**Output**: Applied patch + session memory + wiki insights

---

**Status**: Ready to create clean demo files once Ollama is running.
