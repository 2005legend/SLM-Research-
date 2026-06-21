# Requirements Document

## Introduction

This sprint delivers a comprehensive set of bug fixes, improvements, and infrastructure additions to local-sage — a repo-aware, validation-gated coding agent wrapping Qwen2.5 Coder 7B via Ollama. The work spans six areas: patch path resolution robustness, model output parsing, session memory correctness, benchmark infrastructure, validation gate pre-checking, and documentation. The goal is to raise overall reliability so that the agent can run the full 20-task benchmark suite and produce meaningful pass-rate metrics.

## Glossary

- **Patcher**: The `Patcher` class in `local_sage/validation/patcher.py` responsible for applying unified diff patches to the repository.
- **PatchError**: A new typed exception subclass of `ValidationError` raised when a patch is unparseable or empty.
- **ModelOutputParser**: A new class in `local_sage/agent/parser.py` that extracts a unified diff from raw model output regardless of surrounding text or code fences.
- **ValidationRunner**: The `ValidationRunner` class in `local_sage/validation/runner.py` that orchestrates all four validators.
- **PreValidator**: The fast pre-check logic inside `ValidationRunner.validate_and_apply()` and `ValidationRunner.validate_only()` that runs before the full validator suite.
- **ContractChecker**: The `ContractChecker` class in `local_sage/validation/contracts.py` that performs static analysis against YAML contract files.
- **SessionManager**: The `SessionManager` class in `local_sage/memory/session.py` that persists session state to SQLite.
- **SessionSummary**: The `SessionSummary` dataclass returned by `SessionManager.get_session_summary()`.
- **BenchmarkRunner**: The baseline runner in `evals/baseline.py` that calls Ollama directly with no scaffolding.
- **FixtureRepo**: A self-contained repository under `evals/repos/fixtures/` with intentional bugs, failing tests, and contract YAML files used as benchmark inputs.
- **TaskYAML**: A YAML file under `evals/tasks/` describing one benchmark task with its category, description, fixture repo, and pass condition.
- **ValidationResult**: The `ValidationResult` dataclass that aggregates all validator outputs and is returned by `ValidationRunner`.
- **retry_prompt**: The string produced by `ValidationResult.to_retry_prompt()` fed back to the code generator on a retry cycle.
- **CODE_GENERATOR_SYSTEM_PROMPT**: A module-level constant string in `local_sage/orchestration/nodes.py` used as the system prompt for the code-generation node.
- **cache**: An in-memory dict keyed by SHA-256 patch hash (first 16 hex characters) that stores `ValidationResult` objects within a single `validate_and_apply()` or `validate_only()` call.
- **token_tracking**: The set of fields `prompt_tokens`, `completion_tokens`, `estimated_cost_usd`, `actual_cost_usd` added to session records and surfaced in `sage status`.

---

## Requirements

### Requirement 1: Robust Patch Path Resolution

**User Story:** As a developer running local-sage, I want patch paths to resolve correctly even when the model prefixes them with the repo folder name, so that valid patches are not silently discarded.

#### Acceptance Criteria

1. WHEN `Patcher._apply_single_diff()` is called with a `raw_path` that does not resolve to an existing file after stripping leading `a/` or `b/` prefixes, THE `Patcher` SHALL attempt the following fallback strategies in order before skipping the diff: (a) strip everything before the first occurrence of a known top-level package directory name (`local_sage/`, `tests/`, `evals/`, `wiki/`, `contracts/`); (b) match by filename only as a last resort.
2. WHEN `Patcher._apply_single_diff()` resolves a file path using any fallback strategy, THE `Patcher` SHALL emit a `logger.warning` message containing the literal text `"Patch path"`, the raw path value, and `"using fallback resolution"`.
3. THE `Patcher` SHALL apply the resolved diff to the correct target file when a fallback strategy succeeds.
4. IF no fallback strategy resolves the path to an existing file, THEN THE `Patcher` SHALL explicitly skip the diff (take no action on that diff object) and emit a `logger.warning` identifying the unresolvable path.

---

### Requirement 2: Empty Patch Detection

**User Story:** As a developer, I want the system to raise a clear error when the model outputs explanation text instead of a diff, so that the retry loop receives actionable diagnostics rather than silently applying nothing.

#### Acceptance Criteria

1. WHEN `whatthepatch.parse_patch()` returns an empty list for a given patch string, THE `Patcher` SHALL raise a `PatchError` before entering the diff application loop. IF `whatthepatch.parse_patch()` raises an exception, THE `Patcher` SHALL allow that exception to propagate naturally without wrapping it in `PatchError`.
2. THE `PatchError` message SHALL contain the text `"No valid diff hunks found in patch"` and `"explanation text"`.
3. THE `PatchError` class SHALL be defined in `local_sage/validation/exceptions.py` as a subclass of `ValidationError` with a `patch_preview` attribute holding the first 200 characters of the bad patch string.
4. THE `PatchError` class SHALL be importable from `local_sage.validation.exceptions`.

---

### Requirement 3: Retry Prompt Enhancement for Empty Patches

**User Story:** As a developer, I want the retry prompt to explain that the model produced explanation text rather than a diff, so that the next generation attempt is more likely to produce a valid patch.

#### Acceptance Criteria

1. WHEN `ValidationResult.to_retry_prompt()` is called and the `failures` list contains exactly one `ValidationFailure` whose `tool` is `"ruff"` and `rule_code` values on all `ruff_violations` are `"FORMAT"`, THE `ValidationResult` SHALL append a note to the retry prompt. IF appending the note fails for any reason, THE `ValidationResult` SHALL raise the exception (the retry prompt SHALL NOT be returned without the note).
2. THE appended note SHALL contain the literal text `"unified diff"`, `"--- a/file"`, `"+++ b/file"`, and `"@@ ... @@ hunks"`.
3. WHEN `ValidationResult.to_retry_prompt()` is called and conditions in criterion 1 do not apply, THE `ValidationResult` SHALL produce the same retry prompt as before this change (no regression).

---

### Requirement 4: ContractChecker Reports Missing Source Files

**User Story:** As a developer, I want the ContractChecker to report a failure when a contract's source file is not found, so that missing files do not silently pass contract checks.

#### Acceptance Criteria

1. WHEN `ContractChecker._check_exception_types()` is called and the source file resolved from `contract.source_file` does not exist under `repo_dir`, THE `ContractChecker` SHALL return a `ContractFailure` with `constraint` set to `"source_file_not_found"` and `actual` containing the missing path string. WHILE the source file exists, THE `ContractChecker` SHALL apply its existing exception-type checking logic without modification.
2. THE `ContractChecker` SHALL NOT emit a `logger.warning` and silently return an empty list when the source file is missing; a `ContractFailure` SHALL be returned instead.
3. WHEN `ContractChecker._check_return_shape()` is called and the source file does not exist under `repo_dir`, THE `ContractChecker` SHALL return a `ContractFailure` with `constraint` set to `"source_file_not_found"` before attempting the dynamic import. WHILE the source file exists, THE `ContractChecker` SHALL proceed with the existing return-shape checking logic without modification.

---

### Requirement 5: Session Task Count Correctness

**User Story:** As a developer using `sage status`, I want the displayed task count to reflect the actual number of completed tasks, so that I can track agent productivity accurately.

#### Acceptance Criteria

1. WHEN `SessionManager.record_task()` is called with a valid session ID, task string, patch string, and result object, THE `SessionManager` SHALL insert exactly one row into the `test_results` table for that session.
2. WHEN `SessionManager.get_session_summary()` is called after `N` calls to `record_task()` for the same session, THE `SessionManager` SHALL return a `SessionSummary` whose `task_count` field equals the number of times `record_task()` was called, reflecting attempted calls regardless of database-level insertion success.
3. THE `SessionManager` SHALL count `task_count` by querying `COUNT(*)` from the `test_results` table filtered by `session_id`.
4. IF `record_task()` has never been called for a session, THEN THE `SessionManager` SHALL return a `SessionSummary` with `task_count` equal to `0`.

---

### Requirement 6: Suppress Python 3.14 Deprecation Warnings in Tests

**User Story:** As a developer running the test suite, I want LangChain and LangGraph deprecation warnings suppressed in pytest output, so that test results are readable without noise from third-party libraries.

#### Acceptance Criteria

1. THE `pyproject.toml` `[tool.pytest.ini_options]` section SHALL include a `filterwarnings` list that ignores `DeprecationWarning` from `langchain_core` and `langgraph`.
2. WHEN `pytest` is run, THE test output SHALL NOT display `DeprecationWarning` messages originating from `langchain_core.*` or `langgraph.*` modules. IF the warning suppression configuration is present but ineffective, THE test run SHALL continue and tests SHALL still pass or fail on their own merits (the test run SHALL NOT itself be failed due to suppression being ineffective).
3. THE `filterwarnings` entries SHALL use the `ignore` action with a `module` pattern matching `langchain_core` and `langgraph` respectively.

---

### Requirement 7: Model Output Parser

**User Story:** As a developer, I want a dedicated parser that reliably extracts unified diffs from model output regardless of surrounding text or code fences, so that valid diffs are not discarded due to formatting variation.

#### Acceptance Criteria

1. THE `ModelOutputParser` class SHALL be defined in `local_sage/agent/parser.py` with an `extract_diff()` method that accepts a single `str` argument and returns `str | None`.
2. WHEN `ModelOutputParser.extract_diff()` is called with a string that starts with `---`, THE `ModelOutputParser` SHALL return the full string as the diff.
3. WHEN `ModelOutputParser.extract_diff()` is called with a string containing a diff wrapped in a ```` ```diff ```` code block, THE `ModelOutputParser` SHALL extract and return the diff content without the fence markers.
4. WHEN `ModelOutputParser.extract_diff()` is called with a string containing a diff wrapped in a plain ```` ``` ```` code block, THE `ModelOutputParser` SHALL extract and return the diff content without the fence markers.
5. WHEN `ModelOutputParser.extract_diff()` is called with a string containing explanation text followed by a line beginning with `---`, THE `ModelOutputParser` SHALL extract and return the content starting from the first line that begins with `---`, even if earlier lines in the explanation text also begin with `---`.
6. WHEN `ModelOutputParser.extract_diff()` is called with a string that contains no recognisable diff content, THE `ModelOutputParser` SHALL return `None`.
7. WHEN `ModelOutputParser.extract_diff()` returns `None`, THE `code_generator_node` in `local_sage/orchestration/nodes.py` SHALL set `patch` to an empty string and log a warning containing `"no diff found"`.

---

### Requirement 8: Structured System Prompt for Code Generation

**User Story:** As a developer, I want a dedicated system prompt constant for the code-generation node that strictly constrains model output format, so that the model is less likely to produce explanation text instead of a diff.

#### Acceptance Criteria

1. THE `nodes.py` module SHALL define a module-level string constant named `CODE_GENERATOR_SYSTEM_PROMPT`.
2. THE `CODE_GENERATOR_SYSTEM_PROMPT` SHALL instruct the model to output only a unified diff in git diff format with no explanation, no markdown fences, and no other text.
3. WHEN `code_generator_node` calls `OllamaClient.generate()`, THE `code_generator_node` SHALL pass `CODE_GENERATOR_SYSTEM_PROMPT` as the `system` argument instead of the inline string.
4. THE `CODE_GENERATOR_SYSTEM_PROMPT` SHALL specify the expected line format: lines starting with `---`, `+++`, `@@`, ` ` (context), `+` (addition), or `-` (deletion).

---

### Requirement 9: Benchmark Baseline Runner

**User Story:** As a researcher, I want a baseline runner that measures raw Ollama performance with no scaffolding, so that I can quantify how much improvement the local-sage layers provide.

#### Acceptance Criteria

1. THE `BenchmarkRunner` SHALL be defined in `evals/baseline.py` and callable as `python evals/baseline.py`.
2. WHEN `BenchmarkRunner` runs a task, THE `BenchmarkRunner` SHALL call the Ollama API at `localhost:11434` directly with the task description and SHALL explicitly disable all scaffolding features — repo graph, session memory, wiki context, and retry loop — regardless of system-level configuration defaults.
3. WHEN `BenchmarkRunner` receives a response from Ollama, THE `BenchmarkRunner` SHALL apply the response to a fresh copy of the fixture repo using `Patcher.apply_to_temp()`.
4. WHEN the patch has been applied to the temp copy, THE `BenchmarkRunner` SHALL run pytest, mypy, and ruff against the temp copy and record pass/fail per task.
5. THE `BenchmarkRunner` SHALL record results in the same `BenchmarkReport` / `TaskResult` schema used by `evals/runner.py`.
6. WHEN `BenchmarkRunner` finishes all tasks, THE `BenchmarkRunner` SHALL print a report in the same format as `evals/runner.py` `print_report()`.
7. THE `BenchmarkRunner` SHALL accept `--tasks-dir` and `--repos-dir` CLI arguments with the same defaults as `evals/runner.py`.

---

### Requirement 10: Expanded Benchmark Task Suite

**User Story:** As a researcher, I want 20 benchmark task YAML files covering four categories, so that I can measure agent performance across a representative spread of coding challenges.

#### Acceptance Criteria

1. THE `evals/tasks/` directory SHALL contain exactly 20 task YAML files following the schema accepted by `evals/runner.py` `load_task()`.
2. THE 20 tasks SHALL be distributed as 5 tasks per category across the four categories: `contract_violation`, `edge_case`, `multi_file`, and `context_drift`.
3. EACH task YAML file SHALL contain the fields: `id`, `category`, `description`, `repo`, `expected_files_changed`, and `pass_condition`.
4. THE `pass_condition` field for each task SHALL be a string that can be evaluated to determine pass/fail (e.g., pytest exit code, specific test name passing).
5. EACH task's `repo` field SHALL reference a fixture repo that exists under `evals/repos/fixtures/`.

---

### Requirement 11: Fixture Repositories

**User Story:** As a researcher, I want self-contained fixture repositories with intentional bugs and failing tests, so that benchmark tasks have a consistent and reproducible starting state.

#### Acceptance Criteria

1. THE `evals/repos/fixtures/` directory SHALL contain at least two fixture repos: `simple_api/` and `data_processor/`.
2. EACH fixture repo SHALL contain a `tests/` directory with at least one pytest test that fails before the intended fix is applied.
3. EACH fixture repo SHALL contain at least one pytest test that passes after the intended fix is applied.
4. EACH fixture repo SHALL contain a `contracts/` directory with at least one YAML contract file in the format accepted by `ContractChecker.load_contracts()`.
5. EACH fixture repo SHALL be a valid Python project (containing `pyproject.toml` or `setup.py`) so that pytest, mypy, and ruff can be run against it without additional configuration.

---

### Requirement 12: Token and Cost Tracking

**User Story:** As a developer using `sage status`, I want to see token usage and estimated cost for each session, so that I can monitor resource consumption.

#### Acceptance Criteria

1. THE `SessionSummary` dataclass SHALL include the additional fields: `prompt_tokens` (int), `completion_tokens` (int), `estimated_cost_usd` (float), and `actual_cost_usd` (float).
2. WHEN `SessionManager.record_task()` is called, THE `SessionManager` SHALL accept optional `prompt_tokens` and `completion_tokens` integer arguments (defaulting to `0`) and persist them to the database.
3. WHEN `SessionManager.get_session_summary()` is called, THE `SessionManager` SHALL aggregate `prompt_tokens` and `completion_tokens` by summing all rows for the session.
4. THE `estimated_cost_usd` in `SessionSummary` SHALL be computed as `(prompt_tokens + completion_tokens) * cost_per_token` where `cost_per_token` is a configurable constant representing the cloud-proxy rate.
5. THE `actual_cost_usd` in `SessionSummary` SHALL always be `0.0` because local-sage uses only the local Ollama endpoint and incurs no monetary cost.
6. WHEN `sage status` is run, THE CLI SHALL display `prompt_tokens`, `completion_tokens`, `estimated_cost_usd`, and `actual_cost_usd` from the current session's `SessionSummary`.

---

### Requirement 13: Pre-Validation Patch Quality Check

**User Story:** As a developer, I want the validation pipeline to reject obviously bad patches immediately before running the full validator suite, so that invalid model output fails fast without wasting time on subprocess invocations.

#### Acceptance Criteria

1. WHEN `ValidationRunner.validate_and_apply()` or `ValidationRunner.validate_only()` is called, THE `ValidationRunner` SHALL execute a `PreValidator` check before applying the patch to a temp directory or running pytest/mypy/ruff.
2. THE `PreValidator` check SHALL complete in under 100 milliseconds for any patch string up to 100,000 characters.
3. WHEN `ModelOutputParser.extract_diff()` returns `None` for the patch string, THE `PreValidator` SHALL return a failed `ValidationResult` immediately with a `ValidationFailure` whose `tool` is `"pre_check"` and `message` contains `"no valid diff found"`.
4. WHEN the patch string contains only whitespace after stripping, THE `PreValidator` SHALL return a failed `ValidationResult` immediately with a `ValidationFailure` whose `tool` is `"pre_check"` and `message` contains `"empty patch"`.
5. WHEN the patch string contains no lines beginning with `+` or `-` (excluding `---` and `+++` header lines), THE `PreValidator` SHALL return a failed `ValidationResult` immediately with a `ValidationFailure` whose `tool` is `"pre_check"` and `message` contains `"no change lines"`.
6. WHEN the patch string references a file path that does not exist under the repo root, THE `PreValidator` SHALL return a failed `ValidationResult` immediately with a `ValidationFailure` whose `tool` is `"pre_check"` and `message` containing the missing path.
7. WHEN all `PreValidator` checks pass, THE `ValidationRunner` SHALL proceed to apply the patch to a temp directory and run the full validator suite. THE overall `ValidationResult.passed` value SHALL reflect the outcome of the full validator suite (pytest, mypy, ruff, contracts), not only the `PreValidator` pass status.

---

### Requirement 14: Validation Result Caching

**User Story:** As a developer, I want identical patches to skip re-running the full validator suite, so that repeated submissions of the same patch do not waste time on redundant subprocess calls.

#### Acceptance Criteria

1. THE `ValidationRunner` SHALL maintain an in-memory cache keyed by the first 16 hexadecimal characters of the SHA-256 hash of the patch string.
2. WHEN `validate_and_apply()` or `validate_only()` is called with a patch whose hash key is present in the cache, THE `ValidationRunner` SHALL return the cached `ValidationResult` without running any validators.
3. WHEN `validate_and_apply()` or `validate_only()` is called with a patch whose hash key is NOT present in the cache, THE `ValidationRunner` SHALL run the full validator suite and store the result in the cache before returning.
4. THE cache SHALL be cleared at the start of each `validate_and_apply()` call (not `validate_only()`), so that a new top-level apply cycle always starts with a fresh cache.
5. THE cache SHALL be an instance attribute initialised in `ValidationRunner.__init__()` and SHALL NOT be shared across `ValidationRunner` instances.

---

### Requirement 15: README Documentation

**User Story:** As a developer discovering local-sage, I want a structured README that explains the problem, architecture, quick start, and research contributions, so that I can understand and evaluate the project quickly.

#### Acceptance Criteria

1. THE `README.md` file at the repository root SHALL contain the following top-level sections in the exact order: Problem, How It Works, Quick Start, Benchmark Results, Research Contributions, Acknowledgements. A README that contains all required sections in a different order SHALL NOT be considered compliant.
2. THE "How It Works" section SHALL describe all six layers: model, orchestration, repo graph, session memory, wiki, and validation.
3. THE "Quick Start" section SHALL include the exact shell commands to install dependencies, start Ollama, run `sage start`, and run the benchmark suite.
4. THE "Benchmark Results" section SHALL include a placeholder table with columns for Category, Tasks, Pass Rate (local-sage), and Pass Rate (Baseline), populated with `TBD` values.
5. THE "Research Contributions" section SHALL describe the validation gate (ContractChecker + pytest + mypy + ruff) as the novel contribution.

---

### Requirement 16: Demo Recording Script

**User Story:** As a developer, I want an exact asciinema recording sequence documented, so that I can reproduce a polished demo of the agent's end-to-end operation.

#### Acceptance Criteria

1. THE repository SHALL contain a file at `docs/demo_script.md` that documents the exact sequence of commands and expected outputs for recording a demo with asciinema.
2. THE `demo_script.md` SHALL include steps covering: starting Ollama, running `sage init`, running `sage start` with a representative coding task, observing the validation loop, and observing the final applied patch.
3. THE `demo_script.md` SHALL specify the recommended asciinema record command including the output filename and recommended terminal dimensions.
