# local-sage: A Local Coding Agent Benchmark for Small Language Models

**Author:** `<YOUR_NAME>`  
**Affiliation:** `<UNIVERSITY / LAB / INDEPENDENT>`  
**Email:** `<EMAIL>`  
**GitHub:** [local-sage](https://github.com/2005legend/SLM-Research-)

---

## Abstract

Local coding agents built on small language models (SLMs) are increasingly attractive for privacy-sensitive and cost-constrained development workflows, but their failures are often reported only as aggregate pass/fail outcomes. This obscures whether a failure originates from the model, the orchestration stack, the patching mechanism, or the validation design. This paper presents **local-sage**, a local coding-agent scaffold and benchmark harness for isolating failure sources in code-editing workflows. The framework enforces strict patch semantics, scoped validation, controlled fixtures, and structured retry feedback, enabling comparison across multiple local models under the same execution conditions. Across 4 local models (<10B parameter class) and 3 benchmark tasks, the study identifies distinct failure patterns including ambiguity rejection, exact-match drift, retry exhaustion, and format drift under increased prompt complexity. The results show that within the evaluated models, only Llama 3.1 8B successfully resolved ambiguous edit targets natively under strict patch constraints, while other models (Qwen 2.5 7B, Qwen 3.5 9B, DeepSeek 6.7B) suffered severe format drift or hallucinated patch structures during recovery attempts. These findings suggest that local coding-agent reliability depends not only on raw model quality but also heavily on the interaction between patch format design, ambiguity handling, and retry orchestration.

---

## 1. Introduction

### 1.1 Background
Local coding agents offer developers an appealing alternative to cloud-based assistants by guaranteeing data privacy, minimizing operational costs, and working offline. However, these systems rely on Small Language Models (SLMs) typically in the 7B-9B parameter class, which face significant cognitive limits when juggling strict formatting rules, code comprehension, and spatial targeting.

### 1.2 Problem
Existing end-to-end benchmark scores collapse multiple failure sources into a single metric. A failed patch could be the result of incorrect reasoning, but it could equally be caused by formatting drift, context misalignment, or an over-aggressive static analysis pass on unrelated legacy code.

### 1.3 Research gap
Because current benchmarks do not isolate where a failure originates, developers of local coding assistants lack actionable insights into whether they should invest in better models, softer parsers, or smarter validation layers. 

### 1.4 Contributions
- A strict local coding-agent benchmark harness designed to eliminate confounding variables.
- A failure taxonomy specific to search/replace patch-based code editing.
- A controlled comparison across 4 local models (<10B params) isolating ambiguity handling.
- An analysis of format drift and cognitive overload during retry loops.

---

## 2. Benchmark Design

### 2.1 Benchmark goals
The benchmark is designed to stress not just code generation, but **edit targeting**, **format stability**, **validation resilience**, and **ambiguity resolution**.

### 2.2 Tasks
- **Task 1 & Task 2 (Formatting & Syntax):** Modify isolated string returns (e.g., `returns "C"`). These test baseline instruction adherence, string formatting fidelity, and syntactic validity.
- **Task 3 (The Ambiguity Trap):** Modify a string (`return "hello"`) that occurs in identical fashion in two different functions (`func3` and `func4`). This tests the model's context-disambiguation capability to recognize ambiguity and expand its context window (e.g., including the function signature) to uniquely identify the patch target.

### 2.3 Models
| Model | Params | Type | Local Serving |
|---|---|---|---|
| qwen2.5-coder:7b | 7B | code-specialized | Ollama |
| deepseek-coder:6.7b | 6.7B | code-specialized | Ollama |
| llama3.1:8b | 8B | general / instruct | Ollama |
| qwen3.5:9b | 9B | newer generalist/coding | Ollama |

---

## 3. Results

### 3.1 Quantitative summary

| Model | Task 1 | Task 2 | Task 3 (Ambiguity Trap) | Success Rate |
|-------|------|--------------|-------------------------|-------|
| Llama 3.1 8B | PASS | PASS | PASS | 100% |
| Qwen 2.5 Coder 7B | PASS | PASS | FAIL | 66% |
| Qwen 3.5 9B | PASS | PASS | FAIL | 66% |
| DeepSeek-Coder 6.7B | PASS | PASS | FAIL | 66% |

### 3.2 Qualitative analysis
- **Llama 3.1 8B:** Drifted intent slightly on Task 1 (returning "D" instead of "C") but passed syntactic bounds. Displayed context-disambiguation capability for the Task 3 ambiguity.
- **Qwen 2.5 Coder 7B:** Perfect instruction fidelity on Task 1 and 2. Failed Task 3 due to the identical string `return "hello"`. Could not recover context on retry.
- **DeepSeek-Coder 6.7B / Qwen 3.5 9B:** Exhibited emergent reasoning on Task 2 by autonomously updating the docstring (`"""Return B."""` -> `"""Return D."""`) to match the new return value. However, both failed the Task 3 ambiguity trap. DeepSeek hallucinated completely made-up SEARCH/REPLACE XML syntax on its final retry.

### 3.3 Prompt Engineering & Formatting Under Stress
When Qwen 2.5 Coder 7B was explicitly prompted to expand its context upon failure, it understood the instruction but immediately dropped the `<<<<<<< SEARCH` formatting constraints entirely, reverting to a standard diff format. This highlights the effects of increased prompt complexity, demonstrating that these models struggle to simultaneously balance strict XML-like structural formatting and complex reasoning instructions.

---

## 4. Discussion

### 4.1 Model capability versus orchestration correctness
The benchmark reveals that failures commonly attributed to "poor coding ability" in SLMs are often actually orchestration incompatibilities. Models like Qwen and DeepSeek perfectly understand the semantic requirement but fail to express it in the exact spatial format required by strict SEARCH/REPLACE parsers when ambiguity is present.

### 4.2 Why strict patching is useful diagnostically
Enforcing a rigid `count == 1` rule in the patching layer acts as a perfect diagnostic sieve for spatial reasoning. It proves that within the evaluated models, most <10B models lacked the context-disambiguation capability to realize that a line of code is non-unique within its parent file.

---

## 5. Limitations
- **Syntactic vs. Semantic Verification:** The validation harness relies heavily on syntactic tools (Ruff, MyPy). A model that generates syntactically valid but semantically incorrect code (e.g., Llama returning `"D"` instead of `"C"`) will pass the strict bounds of this benchmark.
- **Model Scale:** This study focused explicitly on the <10B parameter class to evaluate local, highly constrained deployments. Larger models (14B-32B or frontier APIs) are hypothesized to natively navigate the Ambiguity Trap with much higher success rates.

---

## 6. Conclusion
This study demonstrates that the true bottleneck for local coding agents using <10B parameter models is not code generation, but spatial ambiguity resolution and format adherence under stress. While Llama 3.1 8B demonstrated a unique native capacity to expand its edit context, other highly capable coding models (Qwen, DeepSeek) routinely fell into ambiguity traps and suffered severe format drift when prompted to recover. Future local assistant orchestration must either employ softer, fuzzier matching algorithms or utilize models with significantly higher cognitive capacity to handle strict formatting and disambiguation simultaneously.

---

## 7. Future Work

To elevate this framework toward full production-readiness and larger-scale academic evaluation, we identify several critical areas for future improvement:

### 7.1 Hybrid Context Selection & Git History
Current context selection relies on static AST parsing and PageRank over repository symbols. Real-world software context is highly temporal; weighting context retrieval using **git recency**, **co-change frequency**, **bug history**, and **embedding similarity** would likely outperform static structural metrics alone.

### 7.2 Scalability to Frontier Repositories
The current benchmark validates capabilities on scoped dummy fixtures. Future evaluations must scale to real-world repository tasks (e.g., bug fixes in FastAPI, Django, Requests, or NumPy) to measure degradation in success rates as repository context sizes reach the 100k+ token limits.

### 7.3 Runtime Learning & Memory Lifecycle
The retry loop is currently deterministic and prompt-based. Adding an epistemic memory layer where failures are extracted, reasoned over, and pushed to a persistent "lessons learned" wiki would enable runtime learning. Furthermore, this memory requires version-awareness to prevent stale architectural memory from misguiding the agent after major refactors.

### 7.4 Semantic Contracts
While the current validation layer heavily utilizes syntactic constraints (Ruff, MyPy), defining advanced semantic contracts (e.g., invariants, side effects, function purity, and thread safety bounds) would provide much stronger guarantees than interface-level checks.

### 7.5 Quantitative Profiling
Future studies will expand the empirical dataset to include scaling laws, plotting **Context Size vs. Success Rate**, **Retry Budget vs. Patch Success**, and taxonomizing failure rates across a wider spectrum of model sizes (e.g., 7B vs. 14B).
