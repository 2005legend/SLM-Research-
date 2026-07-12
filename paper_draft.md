# Evaluating Small Language Models (SLMs) on Search/Replace Code Editing

## 1. Benchmark Setup & Methodology

This study evaluates the capability of Small Language Models (SLMs) in the <10B parameter class to execute precise code modifications using a strict `SEARCH/REPLACE` patching protocol. To isolate model reasoning capabilities from tooling and backend parsing errors, we utilized a custom, scoped validation harness.

### Controlling Confounders
To ensure repeatable and valid results, the validation harness controlled for the following major variables:
1. **Scoped Validation:** Static analysis (Ruff, MyPy) was restricted strictly to the files modified by the model patch, preventing repo-wide violations from interfering with the task validation signal.
2. **Consistent Fixtures:** Target files (dummy modules) were explicitly harmonized to pass strict linting (e.g., adding module/function docstrings and type annotations) prior to the test. This guarantees that any validation failure stems solely from the model's modification.
3. **Strict Ambiguity Handling:** The matching layer strictly enforces a `original_text.count(search_text) == 1` rule. If a model generates a `SEARCH` block that occurs multiple times in the file, it is automatically rejected as ambiguous, and the model is prompted to retry.

### The Tasks
The benchmark consisted of three atomic tasks:
- **Task 1 & Task 2:** Modify isolated string returns (e.g., `returns "C"`). These test baseline instruction adherence, string formatting fidelity, and syntactic validity.
- **Task 3 (The Ambiguity Trap):** Modify a string (`return "hello"`) that occurs in identical fashion in two different functions (`func3` and `func4`). This tests the model's capacity to recognize ambiguity and natively expand its context window (e.g., including the function signature) to uniquely identify the patch target.

---

## 2. Model Comparison

| Model | Size | Success Rate | T3 Ambiguity Resolution | Notes |
|-------|------|--------------|-------------------------|-------|
| Llama 3.1 | 8B | 100% | Native Pass | Drifted intent on T1 but stayed syntactically valid. Successfully expanded context for T3. |
| Qwen 2.5 Coder | 7B | 66% | Fail (Trap) | Perfect fidelity on T1/T2. Failed to expand context for T3 ambiguity. |
| Qwen 3.5 | 9B | 66% | Fail (Trap) | Emergent reasoning on T2 (updated docstring). Failed T3. |
| DeepSeek-Coder | 6.7B | 66% | Fail (Trap) | Emergent reasoning on T2. Failed T3; hallucinated XML format on final retry. |

---

## 3. Failure Taxonomy

Our tests revealed several distinct failure modes that define the cognitive limits of SLMs in editing tasks.

### A. The Ambiguity Trap (Context Blindness)
Models often generate a `SEARCH` block containing only the exact lines needing modification, failing to recognize when those lines are non-unique within the file. 

**Log Excerpt (Strict Rejection):**
```text
Task task_3 VALIDATION FAIL [pre_check]: No valid diff hunks found in patch — search text occurs 2 times in dummy_multi_3.py. The SEARCH block must be expanded to uniquely identify the location.
```
*Resolution:* This was the primary failure mode for the 7B-9B models (Qwen, DeepSeek). They lacked the spatial reasoning to expand their search context after being rejected.

### B. Format Drift & Instruction Dropping
When subjected to cognitive overload—such as being explicitly prompted to resolve an ambiguity trap while maintaining a strict pseudo-XML syntax format—SLMs frequently "drop" an instruction. 

In testing, when Qwen 2.5 7B was explicitly prompted to expand its context, it understood the task but reverted to generating standard unified diffs instead of the required `<<<<<<< SEARCH` format, causing a parser failure.

**Log Excerpt (Format Drift under Retry):**
```text
_build_local_code_gen_prompt: retry attempt 1 — prepending RETRY_FORMAT_REMINDER
no search-replace blocks found in model output. Raw output:
```diff
--- a/dummy_multi_3.py
+++ b/dummy_multi_3.py
@@ -6,5 +6,5 @@
     """Return hello."""
     return "hello"
 
-def func4() -> str:
+def func4() -> str:
     """Return hello."""
-    return "world"
```
```

### C. Hallucinated Syntax
Under repeated retries and failures, models can lose alignment and hallucinate entirely new syntaxes. For example, DeepSeek-Coder 6.7B on its final retry hallucinated the following:
```text
SEARCH [func4\(\) -> str:  
RETURN hello]  
REPLACE [func4() -> str:  
return "world"]
```

---

## 4. Limitations
- **Syntactic vs. Semantic Verification:** The validation harness relies heavily on syntactic tools (Ruff, MyPy). A model that generates syntactically valid but semantically incorrect code (e.g., returning `"D"` instead of `"C"`) will pass the strict bounds of this benchmark.
- **Model Scale:** This study focused explicitly on the <10B parameter class to evaluate local, highly constrained deployments. Larger models (14B-32B or frontier APIs) are hypothesized to natively navigate the Ambiguity Trap with much higher success rates.
