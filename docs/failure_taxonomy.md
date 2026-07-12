# Failure Taxonomy

This document outlines the distinct failure categories identified during the evaluation of <10B parameter models on patch-based code editing tasks in `local-sage`.

## 1. The Ambiguity Trap (Context Blindness)
**Definition:** The model generates a `SEARCH` block containing the exact lines needing modification, but fails to recognize that those lines are non-unique within the target file.

**Trigger Condition:** Strict ambiguity check in the parser detects `count > 1` for the search text.

**Example Log Snippet:**
```text
Task task_3 VALIDATION FAIL [pre_check]: No valid diff hunks found in patch — search text occurs 2 times in dummy_multi_3.py. The SEARCH block must be expanded to uniquely identify the location.
```

**Interpretation:** This is the primary failure mode for the 7B-9B models (Qwen, DeepSeek). These models lack the spatial reasoning to expand their search context proactively to include unique surrounding lines (like a function definition).

---

## 2. Format Drift & Instruction Dropping
**Definition:** When subjected to cognitive overload—such as being explicitly prompted to resolve an ambiguity trap while maintaining a strict pseudo-XML syntax format—the model "drops" an instruction and outputs an invalid patch format.

**Trigger Condition:** The model is fed a `RETRY_FORMAT_REMINDER` but abandons the `<<<<<<< SEARCH` format for a standard markdown code block or unified diff.

**Example Log Snippet:**
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

**Interpretation:** This demonstrates a hard cognitive ceiling in SLMs. Fixing the ambiguity constraint via explicit prompting often breaks the formatting constraint, leading to a parser failure.

---

## 3. Hallucinated Syntax
**Definition:** Under repeated retries and failures, the model loses alignment entirely and hallucinates non-existent syntax for the patch block.

**Trigger Condition:** The model reaches the 2nd or 3rd retry attempt and produces completely unrecognized structural syntax.

**Example Log Snippet:**
```text
SEARCH [func4\(\) -> str:  
RETURN hello]  
REPLACE [func4() -> str:  
return "world"]
```

**Interpretation:** This was observed heavily in DeepSeek-Coder 6.7B on its final retry attempt. It represents a total breakdown of instruction following under stress.

---

## 4. Validation Noise (Theoretical)
**Definition:** External validation rules, not task semantics, cause the patch to fail.
**Trigger Condition:** A repo-wide linting rule triggers a failure on an unrelated file, or a strict formatting rule (like missing blank lines) fails an otherwise semantically correct patch.
**Interpretation:** We successfully controlled for this in our benchmark by scoping validation only to changed files and harmonizing dummy fixtures before execution.
