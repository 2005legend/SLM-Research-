# Requirements Document

## Introduction

local-sage is a repo-aware, validation-gated coding agent that makes Qwen2.5 Coder 7B production-reliable on consumer hardware (RTX 3060 / 8GB VRAM). It wraps a local 7B model with a structural repo graph, persistent session memory, an agent-maintained wiki, and a deterministic validation gate (pytest + mypy + ruff + contract checker) that only applies patches that pass all checks. The system runs entirely locally with no external API calls.

## Glossary

- **Sage**: The CLI tool and top-level entry point for the local-sage system.
- **Agent**: The LangGraph-orchestrated loop that plans, retrieves context, generates code, validates, and writes memory.
- **OllamaClient**: The HTTP client that communicates with the Ollama inference server at `localhost:11434`.
- **ModelResponse**: The typed response object returned by OllamaClient containing generated text and metadata.
- **RepoIndexer**: The component that parses a Python repository using tree-sitter and builds the SymbolGraph.
- **SymbolGraph**: The NetworkX-backed graph of symbols, imports, and call relationships across the repo.
- **ContextSelector**: The component that selects the most relevant code context for a given task.
- **ImpactAnalyzer**: The component that determines which files are affected by a proposed change.
- **SessionManager**: The SQLite-backed component that persists and retrieves session state across invocations.
- **WikiManager**: The component that reads, writes, and searches the agent's markdown knowledge base.
- **ValidationRunner**: The orchestrator that runs all validation checks (pytest, mypy, ruff, contract checker) on a patch.
- **PytestRunner**: The subprocess wrapper that executes pytest with a timeout and captures structured results.
- **MypyRunner**: The subprocess wrapper that executes mypy with a timeout and captures typed errors.
- **RuffRunner**: The subprocess wrapper that executes ruff check and ruff format with a timeout.
- **ContractChecker**: The component that validates generated code against YAML contract files.
- **Patcher**: The component that applies a validated diff patch to the repository.
- **ValidationResult**: The typed result object from a ValidationRunner run, containing pass/fail status and diagnostics.
- **Patch**: A unified diff representing a proposed code change.
- **Contract**: A YAML file specifying function-level constraints (exception types, return shapes, preconditions).
- **Warm repo**: A repository whose SymbolGraph index has already been built and cached.

---

## Requirements

### Requirement 1: CLI Entry Point

**User Story:** As a developer, I want a single CLI command (`sage`) with subcommands, so that I can control the agent, run tasks, validate patches, and inspect state from the terminal.

#### Acceptance Criteria

1. THE Sage SHALL expose the following subcommands: `start`, `task`, `validate`, `benchmark`, `memory show`, `wiki list`, `wiki show`, and `status`.
2. WHEN the user runs `sage start`, THE Sage SHALL boot the Agent, index the current repository, load the most recent session, and report ready status within 30 seconds on a warm repo.
3. WHEN the user runs `sage task "<description>"`, THE Sage SHALL execute the full agent loop for the given task description and display progress using Rich terminal UI.
4. WHEN the user runs `sage validate --patch <path>`, THE Sage SHALL run the ValidationRunner on the specified patch file and display the ValidationResult without applying the patch.
5. WHEN the user runs `sage status`, THE Sage SHALL display the Ollama model status, SymbolGraph index statistics, and current session summary.
6. WHEN the user runs `sage memory show`, THE Sage SHALL display the current session memory contents in a formatted Rich table.
7. WHEN the user runs `sage wiki list`, THE Sage SHALL display all wiki entries as a formatted list.
8. WHEN the user runs `sage wiki show <entry>`, THE Sage SHALL display the contents of the specified wiki entry.
9. IF an unrecognized subcommand is provided, THEN THE Sage SHALL display a help message listing all valid subcommands and exit with a non-zero status code.
10. THE Sage SHALL be installable via `pip install local-sage` and immediately available as the `sage` command after installation.

---

### Requirement 2: Ollama Model Client

**User Story:** As a developer, I want a typed, async HTTP client for Ollama, so that the agent can generate code reliably without raw HTTP calls scattered across the codebase.

#### Acceptance Criteria

1. THE OllamaClient SHALL communicate exclusively with the Ollama inference server at `localhost:11434` using async HTTP via httpx.
2. WHEN a generation request is made, THE OllamaClient SHALL return a typed ModelResponse containing the generated text, token counts, and finish reason.
3. WHEN the Ollama server is unreachable, THE OllamaClient SHALL raise an `OllamaConnectionError` with a descriptive message.
4. WHEN the Ollama server returns a non-200 HTTP status, THE OllamaClient SHALL raise an `OllamaRequestError` containing the status code and response body.
5. WHEN a generation request exceeds 120 seconds, THE OllamaClient SHALL raise an `OllamaTimeoutError`.
6. THE OllamaClient SHALL use Qwen2.5 Coder 7B as the model and SHALL NOT accept configuration for any other model or external API endpoint.
7. THE OllamaClient SHALL enforce that total memory usage for model inference stays within 4.1GB VRAM by using the quantized model variant.

---

### Requirement 3: Repo Graph Indexing

**User Story:** As a developer, I want the agent to understand the structure of my codebase before making changes, so that it can select relevant context and predict the impact of edits.

#### Acceptance Criteria

1. WHEN `sage start` is run in a Python repository, THE RepoIndexer SHALL parse all `.py` files using tree-sitter and populate the SymbolGraph.
2. THE SymbolGraph SHALL represent functions, classes, imports, and call relationships as typed nodes and edges in a NetworkX graph.
3. WHEN the SymbolGraph has been built, THE RepoIndexer SHALL persist the index to disk so that subsequent `sage start` invocations on a warm repo complete within 30 seconds.
4. WHEN a file is modified, THE RepoIndexer SHALL update only the affected nodes and edges in the SymbolGraph rather than rebuilding the entire index.
5. WHEN given a task description, THE ContextSelector SHALL return the top-K most relevant symbols and their source spans, ranked by structural proximity and semantic relevance.
6. WHEN given a proposed Patch, THE ImpactAnalyzer SHALL return the set of files and symbols that the patch modifies or that transitively depend on modified symbols.
7. IF a `.py` file contains a syntax error, THEN THE RepoIndexer SHALL log the error, skip that file, and continue indexing the remaining files.

---

### Requirement 4: Session Memory

**User Story:** As a developer, I want the agent to remember context from previous sessions, so that I can continue multi-day coding tasks without re-explaining the codebase.

#### Acceptance Criteria

1. THE SessionManager SHALL persist session state to a SQLite database using only the Python standard library `sqlite3` module.
2. WHEN a session ends, THE SessionManager SHALL store the task history, applied patches, and agent observations for that session.
3. WHEN `sage start` is run, THE SessionManager SHALL load the most recent session and make its context available to the Agent.
4. WHEN a semantic query is issued against session memory, THE SessionManager SHALL use Mem0 with local sentence-transformers embeddings to retrieve the most relevant past observations.
5. THE SessionManager SHALL operate within 2GB of system RAM for the embeddings model and index.
6. IF the SQLite database file is missing or corrupted, THEN THE SessionManager SHALL create a new empty database and log a warning.

---

### Requirement 5: Agent Wiki

**User Story:** As a developer, I want the agent to maintain its own knowledge base about the repo, so that it can accumulate and reuse insights across tasks without relying solely on session memory.

#### Acceptance Criteria

1. THE WikiManager SHALL store wiki entries as plain markdown files in a designated directory within the repository.
2. WHEN the Agent completes a task, THE WikiManager SHALL write or update a wiki entry summarizing the changes made and any relevant observations.
3. WHEN the Agent begins a task, THE WikiManager SHALL search existing wiki entries for relevant content and include matching entries in the task context.
4. WHEN the user runs `sage wiki list`, THE WikiManager SHALL return a list of all wiki entry titles and their last-modified timestamps.
5. WHEN the user runs `sage wiki show <entry>`, THE WikiManager SHALL return the full markdown content of the specified entry.
6. IF a wiki entry file cannot be read due to a filesystem error, THEN THE WikiManager SHALL raise a `WikiReadError` with the file path and underlying OS error.

---

### Requirement 6: Validation Gate

**User Story:** As a developer, I want every generated patch to be automatically validated before it is applied, so that the agent never introduces code that fails tests, type checks, or linting.

#### Acceptance Criteria

1. THE ValidationRunner SHALL execute PytestRunner, MypyRunner, RuffRunner, and ContractChecker on every Patch before the Patcher applies it.
2. WHEN all four validators pass, THE ValidationRunner SHALL return a ValidationResult with `passed=True` and apply the Patch via the Patcher.
3. WHEN any validator fails, THE ValidationRunner SHALL return a ValidationResult with `passed=False`, include the diagnostics from the failing validator(s), and SHALL NOT apply the Patch.
4. THE PytestRunner SHALL execute pytest as a subprocess with a configurable timeout defaulting to 60 seconds and return structured pass/fail/error counts.
5. THE MypyRunner SHALL execute mypy as a subprocess with a configurable timeout defaulting to 60 seconds and return a list of typed `MypyError` objects.
6. THE RuffRunner SHALL execute `ruff check` and `ruff format --check` as subprocesses with a configurable timeout defaulting to 30 seconds and return structured lint violations.
7. WHEN a subprocess call to pytest, mypy, or ruff exceeds its configured timeout, THE ValidationRunner SHALL raise a `ValidationTimeoutError` identifying which tool timed out.
8. THE ContractChecker SHALL load YAML contract files from the repository and verify that generated functions match the specified exception types, return shapes, and preconditions.
9. IF a YAML contract file is malformed, THEN THE ContractChecker SHALL raise a `ContractParseError` with the file path and the specific parse failure.
10. THE ValidationRunner SHALL complete all checks within 60 seconds per attempt on the hardware target.
11. WHERE the `--manual-review` flag is set on the validation layer, THE ValidationRunner SHALL require explicit user confirmation before the Patcher applies any patch, regardless of validation outcome.

---

### Requirement 7: Agent Orchestration Loop

**User Story:** As a developer, I want the agent to follow a structured plan-retrieve-generate-validate-remember loop, so that code generation is grounded in repo context and every output is validated before being applied.

#### Acceptance Criteria

1. THE Agent SHALL implement the orchestration loop as a LangGraph StateGraph with the following nodes: `planner`, `context_retriever`, `code_generator`, `validator`, and `memory_writer`.
2. WHEN a task is submitted, THE Agent SHALL execute nodes in the order: `planner` → `context_retriever` → `code_generator` → `validator` → `memory_writer`.
3. WHEN the `validator` node returns a ValidationResult with `passed=False`, THE Agent SHALL re-enter the `code_generator` node with the diagnostics appended to the prompt, up to a configurable maximum retry count defaulting to 3.
4. WHEN the maximum retry count is reached without a passing ValidationResult, THE Agent SHALL report failure to the user with the final diagnostics and SHALL NOT apply any patch.
5. THE Agent SHALL pass the full LangGraph state (task, context, patch, validation result) between nodes as a typed `AgentState` dataclass.
6. WHEN the `memory_writer` node executes, THE Agent SHALL persist the task, the applied patch, and the final ValidationResult to the SessionManager and update the WikiManager.
7. THE Agent SHALL operate within 8GB VRAM and 16GB system RAM at all times during the orchestration loop.

---

### Requirement 8: Hardware and Performance Constraints

**User Story:** As a developer, I want the agent to run entirely on consumer hardware without cloud API calls, so that my code remains private and I avoid ongoing API costs.

#### Acceptance Criteria

1. THE Sage SHALL make no outbound network requests to any endpoint other than `localhost:11434` during normal operation.
2. THE Sage SHALL operate within 8GB VRAM and 16GB system RAM at all times.
3. WHEN run on a warm repo, THE Sage SHALL reach ready state within 30 seconds of `sage start`.
4. THE ValidationRunner SHALL complete all validation checks within 60 seconds per attempt.
5. THE Sage SHALL achieve a pass rate greater than 60% on a 50-task evaluation benchmark, where pass is defined as generated code that passes pytest, mypy, and ruff on the target repository.
6. WHEN run on a cold repo (no existing index), THE Sage SHALL complete initial indexing and reach ready state within 120 seconds for repositories up to 100,000 lines of Python.

---

### Requirement 9: Code Quality and Packaging

**User Story:** As a developer, I want the codebase to follow strict quality standards and be installable in one command, so that the project is maintainable and easy to adopt.

#### Acceptance Criteria

1. THE Sage SHALL be packaged with a `pyproject.toml` that defines all dependencies with pinned versions and exposes the `sage` entry point as `sage = "local_sage.__main__:main"`.
2. THE Sage SHALL require Python 3.11 or higher as specified in `pyproject.toml`.
3. EVERY public function and method in `local_sage/` SHALL have a type hint on every parameter and return value.
4. EVERY public class and method in `local_sage/` SHALL have a Google-style docstring.
5. EVERY module in `local_sage/` SHALL have a corresponding test file under `tests/` mirroring the source path.
6. THE Sage SHALL use `pathlib.Path` for all file I/O operations and SHALL NOT use raw string paths.
7. EVERY custom exception in `local_sage/` SHALL be a typed subclass of a domain-specific base exception and SHALL NOT be a bare `Exception` raise.
8. EVERY function in `local_sage/` SHALL be 40 lines or fewer; functions exceeding this limit SHALL be split into smaller functions.
