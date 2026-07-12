# Benchmark Protocol

This document details the exact tasks, parsing rules, and fixture reset protocols used in the local-sage benchmark harness.

## 1. Tasks
The benchmark evaluates models across three atomic file-editing tasks:

| Task ID | Target File | Instruction | Description |
|---|---|---|---|
| task_1 | `dummy_multi_1.py` | `Modify dummy_multi_1.py so func1 returns "C"` | Direct single-file edit. Tests baseline string formatting fidelity. |
| task_2 | `dummy_multi_2.py` | `Modify dummy_multi_2.py so func2 returns "D"` | Formatting-sensitive edit. Tests ability to maintain syntactic validity while modifying return values. |
| task_3 | `dummy_multi_3.py` | `Modify dummy_multi_3.py so func4 returns "world"` | Ambiguous multi-match edit. The target string `return "hello"` occurs twice in the file. Tests ambiguity resolution and context expansion. |

## 2. Patch Format Contract
Models are instructed to output patches strictly in the following pseudo-XML format:

```text
<<<<<<< SEARCH
[exact text to find]
=======
[replacement text]
>>>>>>> REPLACE
```

## 3. Strict Parsing Rules
The `Patcher` layer enforces a rigid ambiguity guard:
- **Rule:** `original_text.count(search_text) == 1`
- If the text inside the `SEARCH` block occurs exactly once in the target file, the patch is applied.
- If the text occurs more than once (e.g., `count == 2`), the patch is rejected immediately with a `pre_check` ambiguity error. The model is then prompted to retry by expanding its `SEARCH` block context.

## 4. Validation Commands
Validation is strictly scoped to the exact files modified by the patch to prevent unrelated repository-wide lint errors from causing false failures.
- **Ruff:** `ruff check [changed_file_path]`
- **MyPy:** `mypy [changed_file_path]`
- **Pytest:** `pytest [relevant_test_file_path]`

## 5. Fixture Reset Protocol
Before each task, the target dummy modules (`dummy_multi_1.py`, `dummy_multi_2.py`, `dummy_multi_3.py`) are dynamically regenerated to a pristine, Ruff/MyPy compliant state. This guarantees that any validation failures are the direct result of the model's patch, not pre-existing formatting issues.

## 6. Execution Parameters
- **Retry Budget:** 3 retries per task.
- **Environment:** Ollama local model serving.
- **Repo State:** Frozen at the `main` branch tag at the time of Phase 1 conclusion.
