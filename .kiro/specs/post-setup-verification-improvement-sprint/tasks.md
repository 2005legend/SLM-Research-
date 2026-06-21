# Implementation Plan: Post-Setup Verification Improvement Sprint

## Overview

This sprint hardens local-sage across six areas: patch path resolution, model output parsing,
session memory correctness, benchmark infrastructure, validation gate pre-checking, and documentation.
All changes are in Python 3.11+, using pathlib.Path for all file I/O and type hints on every function.
The validation layer (`local_sage/validation/`) requires manual review before any generated code is accepted.

---

## Tasks

- [x] 1. Bootstrap: create `local_sage/agent/` sub-package and configure pyproject.toml
  - [x] 1.1 Create `local_sage/agent/__init__.py` exporting `ModelOutputParser` and `tests/agent/__init__.py`
    - Create `local_sage/agent/__init__.py` with a placeholder `__all__ = ["ModelOutputParser"]`
    - Create `tests/agent/__init__.py` (empty, signals test package)
    - _Requirements: 7.1_
  - [x] 1.2 Add `filterwarnings` entries to `pyproject.toml` `[tool.pytest.ini_options]`
    - Add two `ignore` entries matching `langchain_core.*` and `langgraph.*` with `DeprecationWarning`
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 2. Implement `PatchError` exception class
  - [x] 2.1 Define `PatchError` in `local_sage/validation/exceptions.py`
    - Subclass `ValidationError`; add `patch_preview: str` attribute (first 200 chars of bad patch)
    - Constructor signature: `__init__(self, message: str, patch_preview: str) -> None`
    - Google-style docstring on class and `__init__`
    - _Requirements: 2.3, 2.4_
  - [x]* 2.2 Write property test for `PatchError` message content (Property 6)
    - **Property 6: `PatchError` message always contains both required substrings**
    - **Validates: Requirements 2.1, 2.2**
    - In `tests/validation/test_exceptions.py`: use `hypothesis` `st.text()` for non-diff strings;
      assert message contains `"No valid diff hunks found in patch"` and `"explanation text"`
    - _Requirements: 2.1, 2.2_

- [x] 3. Implement `ModelOutputParser` in `local_sage/agent/parser.py`
  - [x] 3.1 Create `local_sage/agent/parser.py` with the `ModelOutputParser` class and `extract_diff()` method
    - Implement extraction priority: raw `---` start → ` ```diff ` fence → plain ` ``` ` fence with `---`
      → first line starting with `---` followed by `+++` → return `None`
    - Pure string logic, no I/O, stdlib only; type hint `extract_diff(self, raw: str) -> str | None`
    - Google-style docstring on class and method; max 40 lines per function
    - Update `local_sage/agent/__init__.py` to export `ModelOutputParser`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - [x]* 3.2 Write property tests for `ModelOutputParser` (Properties 3, 8)
    - **Property 8: `ModelOutputParser` is idempotent on raw diffs** — `st.text()` prefixed with `"--- a/"`;
      assert `extract_diff(s) == s`
    - **Property 3 (partial): `extract_diff` result always contains `---` if not `None`** —
      `st.text()`; assert `"---" in result` whenever result is not `None`
    - **Validates: Requirements 7.2, 7.6**
    - In `tests/agent/test_parser.py`
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 4. Implement `Patcher` fallback path resolution and `PatchError` raise
  - **⚠️ Validation layer — requires manual review before acceptance**
  - [x] 4.1 Add `_resolve_file_path()` method to `Patcher` in `local_sage/validation/patcher.py`
    - Implement the three-step fallback algorithm (strip `a/`/`b/` → known-root prefix strip →
      `rglob` by filename); all paths scoped to `target_dir` (no traversal outside)
    - Emit `logger.warning` containing `"Patch path"`, `raw_path`, and `"using fallback resolution"` on fallback
    - Emit `logger.warning` identifying unresolvable path when all strategies fail
    - All path operations use `pathlib.Path`; type hint `(self, raw_path: str, target_dir: Path) -> Path | None`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 4.2 Update `_apply_single_diff()` to use `_resolve_file_path()` and raise `PatchError` on empty diff
    - Replace inline path resolution with call to `_resolve_file_path()`
    - After `diffs = list(whatthepatch.parse_patch(patch))`, raise `PatchError` if `not diffs`
    - Allow exceptions from `whatthepatch.parse_patch()` to propagate naturally (no wrapping)
    - _Requirements: 1.3, 2.1, 2.2_
  - [x]* 4.3 Write property test for fallback path resolution (Property 1)
    - **Property 1: Fallback resolution never silently discards a resolvable diff**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    - In `tests/validation/test_patcher.py`: use `hypothesis` + `tmp_path`; for any resolved path,
      assert `path.exists() == True`; for `None`, assert warning was emitted
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 5. Checkpoint — ensure validation layer changes compile and existing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update `ValidationResult.to_retry_prompt()` with diff-format note
  - **⚠️ Validation layer — requires manual review before acceptance**
  - [x] 6.1 Add `_append_diff_format_note()` helper and update `to_retry_prompt()` in `local_sage/validation/result.py`
    - Detect FORMAT-only ruff failure pattern (exactly one failure, `tool == "ruff"`, all `rule_code == "FORMAT"`)
    - Appended note must contain: `"unified diff"`, `"--- a/file"`, `"+++ b/file"`, `"@@ ... @@ hunks"`
    - On failure in `_append_diff_format_note()`, raise the exception (do not return without the note)
    - Non-matching cases return the same prompt as before (no regression)
    - _Requirements: 3.1, 3.2, 3.3_
  - [x]* 6.2 Write unit tests for retry prompt enhancement
    - Test FORMAT-only ruff failure triggers the note and note contains all four required substrings
    - Test non-matching failure returns unmodified prompt (regression guard)
    - In `tests/validation/test_result.py`
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 7. Update `ContractChecker` to report missing source files
  - **⚠️ Validation layer — requires manual review before acceptance**
  - [x] 7.1 Modify `_check_exception_types()` in `local_sage/validation/contracts.py`
    - When `source_path.is_file()` is `False`, return `[ContractFailure(constraint="source_file_not_found", actual=str(source_path))]`
    - Remove the `logger.warning` + empty-list return for the missing-file case
    - _Requirements: 4.1, 4.2_
  - [x] 7.2 Modify `_check_return_shape()` in `local_sage/validation/contracts.py`
    - When `(repo_dir / contract.source_file).is_file()` is `False`, return `[ContractFailure(constraint="source_file_not_found", actual=str(...))]` before the dynamic import
    - Remove the `logger.warning` + empty-list return for the missing-file case
    - _Requirements: 4.3_
  - [x]* 7.3 Write property test for `ContractChecker` missing-file behaviour (Property 7)
    - **Property 7: `ContractChecker` never silently passes a missing source file**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - In `tests/validation/test_contracts.py`: generate contracts with non-existent source files;
      assert both methods return a list containing a `ContractFailure` with `constraint == "source_file_not_found"`
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 8. Fix `SessionManager` task count and add token/cost tracking
  - [x] 8.1 Add `prompt_tokens` and `completion_tokens` columns and update schema migration in `local_sage/memory/session.py`
    - Add `ALTER TABLE test_results ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0`
    - Add `ALTER TABLE test_results ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0`
    - Run migration idempotently (check `PRAGMA table_info` before altering)
    - All DB operations use parameterised queries
    - _Requirements: 12.2_
  - [x] 8.2 Update `SessionSummary` dataclass and `record_task()` signature
    - Add `prompt_tokens: int`, `completion_tokens: int`, `estimated_cost_usd: float`, `actual_cost_usd: float` to `SessionSummary`
    - Update `record_task()` to accept optional `prompt_tokens: int = 0` and `completion_tokens: int = 0`
    - Define `COST_PER_TOKEN` as a module-level constant (e.g. `0.000_002`)
    - _Requirements: 5.1, 12.1, 12.2_
  - [x] 8.3 Fix `get_session_summary()` to add `SUM()` token aggregation and cost fields
    - NOTE: `task_count` via `COUNT(*)` was already implemented — only the token/cost aggregation was new
    - Added `COALESCE(SUM(prompt_tokens), 0)` and `COALESCE(SUM(completion_tokens), 0)` queries
    - Set `estimated_cost_usd = (prompt_tokens + completion_tokens) * COST_PER_TOKEN`
    - Set `actual_cost_usd = 0.0` always
    - _Requirements: 5.2, 5.3, 5.4, 12.3, 12.4, 12.5_
  - [x]* 8.4 Write property tests for session task count and cost (Properties 4, 5)
    - **Property 4: `task_count` equals the number of `record_task` calls** — `st.integers(min_value=0, max_value=20)`;
      after N calls assert `task_count == N`
    - **Property 5: `actual_cost_usd` is always zero** — `st.integers(min_value=0, max_value=100_000)` for token counts;
      assert `summary.actual_cost_usd == 0.0`
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 12.5**
    - In `tests/memory/test_session.py`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 12.3, 12.4, 12.5_

- [x] 9. Checkpoint — ensure memory and validation layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Add `PreValidator` pre-check and SHA-256 result cache to `ValidationRunner`
  - **⚠️ Validation layer — requires manual review before acceptance**
  - [x] 10.1 Add `_cache` instance attribute and SHA-256 caching logic to `ValidationRunner.__init__()` and `validate_and_apply()`
    - Initialise `self._cache: dict[str, ValidationResult] = {}` in `__init__`
    - At the start of `validate_and_apply()`, call `self._cache.clear()`
    - After full validation, store result under `key = hashlib.sha256(patch.encode()).hexdigest()[:16]`
    - In both `validate_and_apply()` and `validate_only()`, return cached result if key present (skip after pre-check)
    - Cache is instance-level only — no class-level sharing
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  - [x] 10.2 Implement `_pre_validate()` method in `ValidationRunner`
    - Evaluate rules in order: empty/whitespace → no recognisable diff (`ModelOutputParser`) → no change lines →
      missing file path; return `ValidationResult(passed=False, failures=[ValidationFailure(tool="pre_check", ...)])` on first failure
    - Return `None` when all checks pass
    - Must complete in < 100 ms for any patch ≤ 100,000 characters; no filesystem writes
    - Wire `_pre_validate()` into both `validate_and_apply()` and `validate_only()` before `apply_to_temp()`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_
  - [x]* 10.3 Write property tests for `PreValidator` (Property 2) and cache (Property 3)
    - **Property 2: Pre-validation never allows an empty patch to reach `apply_to_temp`** —
      `st.text(max_size=1000).filter(lambda s: not s.strip())`; assert `passed=False` and `tool=="pre_check"` and `"empty patch" in message`
    - **Property 3: SHA-256 cache does not affect result correctness** — call `validate_only(p)` twice;
      assert identical `ValidationResult` fields both times
    - **Validates: Requirements 13.1, 13.4, 14.2, 14.5**
    - In `tests/validation/test_runner.py`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 11. Update `nodes.py` with `CODE_GENERATOR_SYSTEM_PROMPT` and `ModelOutputParser` integration
  - [x] 11.1 Define `CODE_GENERATOR_SYSTEM_PROMPT` constant and wire `ModelOutputParser` into `code_generator_node`
    - Add module-level `CODE_GENERATOR_SYSTEM_PROMPT: str` constant specifying: output only a unified diff,
      no explanation, no fences, lines start with `---`, `+++`, `@@`, ` `, `+`, or `-`
    - Pass `CODE_GENERATOR_SYSTEM_PROMPT` as `system=` argument to `OllamaClient.generate()`
    - Call `ModelOutputParser().extract_diff(raw_response)` on the model output
    - If `extract_diff()` returns `None`, set `patch = ""` and log `logger.warning("no diff found in model output")`
    - _Requirements: 7.7, 8.1, 8.2, 8.3, 8.4_
  - [x]* 11.2 Write unit tests for `code_generator_node` with mocked `OllamaClient`
    - Test that `CODE_GENERATOR_SYSTEM_PROMPT` is passed to `generate()`
    - Test that `None` from `extract_diff()` results in `patch = ""` and a logged warning
    - In `tests/orchestration/test_nodes.py`
    - _Requirements: 7.7, 8.3_

- [x] 12. Update `sage status` CLI display for token/cost fields
  - [x] 12.1 Update the `sage status` command in `local_sage/__main__.py` (or `cli.py`) to display token/cost rows
    - Render `prompt_tokens`, `completion_tokens`, `estimated_cost_usd`, `actual_cost_usd` from `SessionSummary`
    - Use Rich `Panel` / `Table` consistent with existing status display style
    - _Requirements: 12.6_

- [x] 13. Checkpoint — ensure full test suite passes end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Build fixture repositories under `evals/repos/fixtures/`
  - [x] 14.1 Create `evals/repos/fixtures/simple_api/` fixture repository
    - Create `pyproject.toml` (minimal Python project, pytest/mypy/ruff runnable)
    - Create `simple_api/core.py` with one intentional bug (e.g. divide-by-zero or wrong exception type)
    - Create `tests/test_before.py` with at least one test that fails before the fix
    - Create `tests/test_after.py` with at least one test that passes after the fix
    - Create `contracts/core_contract.yaml` in the format accepted by `ContractChecker.load_contracts()`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  - [x] 14.2 Create `evals/repos/fixtures/data_processor/` fixture repository
    - Create `pyproject.toml`, `data_processor/processor.py` (intentional bug), `tests/test_before.py`,
      `tests/test_after.py`, `contracts/processor_contract.yaml`
    - Follow the same structure and standards as `simple_api/`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 15. Create 20 benchmark task YAML files under `evals/tasks/`
  - [x] 15.1 Write 5 `contract_violation` task YAML files (`evals/tasks/contract_violation_0{1-5}.yaml`)
    - Each file contains: `id`, `category: contract_violation`, `description`, `repo` (references a fixture),
      `expected_files_changed`, `pass_condition`
    - `pass_condition` is a runnable pytest command string
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 15.2 Write 5 `edge_case` task YAML files (`evals/tasks/edge_case_0{1-5}.yaml`)
    - Same schema; `category: edge_case`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 15.3 Write 5 `multi_file` task YAML files (`evals/tasks/multi_file_0{1-5}.yaml`)
    - Same schema; `category: multi_file`; `expected_files_changed` lists multiple files
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [x] 15.4 Write 5 `context_drift` task YAML files (`evals/tasks/context_drift_0{1-5}.yaml`)
    - Same schema; `category: context_drift`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 16. Implement `BenchmarkRunner` in `evals/baseline.py`
  - [x] 16.1 Create `evals/baseline.py` with the `BenchmarkRunner` class skeleton and CLI entry point
    - Define `BenchmarkRunner.__init__(self, tasks_dir: Path, repos_dir: Path) -> None`
    - Add `argparse` CLI with `--tasks-dir` and `--repos-dir` (same defaults as `evals/runner.py`)
    - Wire `__main__` block to call `BenchmarkRunner(...).run_all()`; print report via `print_report()`
    - _Requirements: 9.1, 9.7_
  - [x] 16.2 Implement `BenchmarkRunner._call_ollama()` and `run_task()`
    - `_call_ollama()` posts directly to `http://localhost:11434/api/generate` via `httpx` with no `OllamaClient` wrapping
    - All scaffolding explicitly disabled: no repo graph, no session memory, no wiki, no retry loop
    - `run_task()` applies the response to a fresh temp copy via `Patcher.apply_to_temp()`; runs pytest/mypy/ruff;
      returns `TaskResult` using the same schema as `evals/runner.py`
    - _Requirements: 9.2, 9.3, 9.4, 9.5_
  - [x] 16.3 Implement `BenchmarkRunner.run_all()` and report printing
    - Collect `TaskResult` objects into a `BenchmarkReport`; print using the same `print_report()` function from `evals/runner.py`
    - _Requirements: 9.5, 9.6_
  - [x]* 16.4 Write unit tests for `BenchmarkRunner` with mocked Ollama and fixture repos
    - Mock `httpx.post` to return a synthetic diff; assert `TaskResult.passed` is set correctly
    - Test missing fixture repo returns `TaskResult(passed=False, error="Fixture repo not found: ...")`
    - In `tests/integration/test_baseline.py` (gate with `SAGE_INTEGRATION=true` env var)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 17. Write README.md documentation
  - [x] 17.1 Write the structured `README.md` at the repository root
    - Include sections in exact order: Problem, How It Works, Quick Start, Benchmark Results,
      Research Contributions, Acknowledgements
    - "How It Works" describes all six layers (model, orchestration, repo graph, session memory, wiki, validation)
    - "Quick Start" includes exact shell commands: install deps, start Ollama, `sage start`, benchmark suite
    - "Benchmark Results" table with columns: Category, Tasks, Pass Rate (local-sage), Pass Rate (Baseline); values `TBD`
    - "Research Contributions" describes the validation gate (ContractChecker + pytest + mypy + ruff) as the novel contribution
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 18. Write demo recording script
  - [x] 18.1 Create `docs/demo_script.md`
    - Document exact sequence: start Ollama → `sage init` → `sage start` with representative task →
      observe validation loop → observe final applied patch
    - Include recommended `asciinema record` command with output filename and terminal dimensions
    - _Requirements: 16.1, 16.2, 16.3_

- [x] 19. Final checkpoint — full test suite, lint, and type check
  - Ensure all tests pass (`pytest`), type checks pass (`mypy .`), and lint is clean (`ruff check .`). Ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- All code in `local_sage/validation/` **requires manual review** before being marked complete — this is a hard constraint from the steering rules
- `Patcher` must use `whatthepatch` for all diff application — never the system `patch` utility
- All file I/O uses `pathlib.Path`; all functions carry type hints; all public classes/methods have Google-style docstrings
- Max function length is 40 lines — split helpers as needed
- Property tests use `hypothesis` (already in dev deps); each property is its own sub-task
- Checkpoints validate incremental progress and surface issues early
- Integration tests in `tests/integration/` are gated by `SAGE_INTEGRATION=true` to avoid requiring a live Ollama server in CI

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "6.1", "7.1", "7.2", "8.1"] },
    { "id": 4, "tasks": ["4.3", "6.2", "7.3", "8.2", "10.1"] },
    { "id": 5, "tasks": ["8.3", "8.4", "10.2", "11.1"] },
    { "id": 6, "tasks": ["10.3", "11.2", "12.1"] },
    { "id": 7, "tasks": ["14.1", "14.2"] },
    { "id": 8, "tasks": ["15.1", "15.2", "15.3", "15.4"] },
    { "id": 9, "tasks": ["16.1"] },
    { "id": 10, "tasks": ["16.2"] },
    { "id": 11, "tasks": ["16.3", "17.1", "18.1"] },
    { "id": 12, "tasks": ["16.4"] }
  ]
}
```
