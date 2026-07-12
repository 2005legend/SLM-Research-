# local-sage

<p align="center">
  <strong>Local coding-agent scaffold and benchmark harness for studying reliability boundaries in small language models.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" />
  <img src="https://img.shields.io/badge/Ollama-local%20LLM-black" />
  <img src="https://img.shields.io/badge/License-MIT-green" />
  <img src="https://img.shields.io/badge/Status-Research%20Prototype-orange" />
</p>

<p align="center">
  <a href="#overview">Overview</a> •
  <a href="#motivation">Motivation</a> •
  <a href="#research-question">Research Question</a> •
  <a href="#benchmark">Benchmark</a> •
  <a href="#results">Results</a> •
  <a href="#repository-structure">Repository Structure</a> •
  <a href="#setup">Setup</a> •
  <a href="#citation">Citation</a>
</p>

---

## Overview

**local-sage** is a local, repo-aware coding assistant and research benchmark framework designed to evaluate how small and mid-sized local language models behave on code-editing tasks under strict validation and patch-application constraints.

The project began as an attempt to scaffold a practical local coding assistant for bug fixing and small development tasks. It later evolved into a controlled benchmark and failure-analysis framework for studying reliability boundaries in local coding agents.

### Core contributions
- A local coding-agent scaffold targeting resource-constrained hardware.
- A strict patch-validation and application pipeline.
- A benchmark harness for controlled multi-model comparisons.
- A failure taxonomy for ambiguity, formatting drift, and retry exhaustion.
- A reproducible experimental setup for studying model capability versus orchestration correctness.

---

## Motivation

Current local coding-agent setups often report only end-to-end success or failure, which hides the true source of failure. In practice, failures may originate from weak context selection, patch-format drift, ambiguous search blocks, validation noise, retry-loop collapse, or actual model reasoning limitations.

This repository is built around the idea that a coding agent should not only be evaluated by whether it “works,” but by **where** it fails, **why** it fails, and whether those failures are attributable to the model, the harness, or the validation stack.

---

## Research Question

> **Which failure modes in local coding agents are caused by the model itself, and which are caused by orchestration, patch matching, context selection, or validation design?**

---

## Benchmark

The benchmark is designed to stress not just code generation, but **edit targeting**, **format stability**, **validation resilience**, and **ambiguity resolution**.

### Task classes
| Task Type | Description | Example Failure Signal |
|---|---|---|
| Direct single-file edit | Small local edit with clear unique target | incorrect replacement |
| Formatting-sensitive edit | Correct semantic change but style/format must remain valid | ruff violation |
| Ambiguous multi-match edit | Search text matches multiple locations | pre-check ambiguity rejection |
| Retry-recovery task | Model must recover from a prior rejection | syntax drift / parse failure |

---

## Results

### Summary table

| Model | Task 1 | Task 2 | Task 3 (Ambiguity) | Main Failure Mode |
|---|---|---|---|---|
| llama3.1:8b | PASS | PASS | PASS | Native context expansion |
| deepseek-coder:6.7b | PASS | PASS | FAIL | Pre-check ambiguity rejection & hallucinated syntax |
| qwen2.5-coder:7b | PASS | PASS | FAIL | Pre-check ambiguity rejection & Format drift |
| qwen3.5:9b | PASS | PASS | FAIL | Pre-check ambiguity rejection |

### Failure taxonomy

| Category | Description |
|---|---|
| Pre-check ambiguity | SEARCH text matched multiple valid locations and was correctly rejected |
| Format drift | Model abandoned required patch syntax and emitted unified diff or prose under cognitive load |
| Hallucinated syntax | Model hallucinated completely invalid XML patch structures on retry |
| Retry exhaustion | Model received structured feedback but failed to recover within retry budget |

### Main finding
The benchmark clearly isolates ambiguity-handling failures under strict patch matching. The results suggest that models in the <10B parameter class (with the exception of Llama 3.1 8B) lack the native reasoning capability to expand their search context windows when targeting ambiguous code lines. Furthermore, explicitly prompting these models to fix the ambiguity often induces cognitive overload, resulting in severe format drift or hallucinated patch structures.

---

## Roadmap / Future Work

- **Hybrid Context Selection:** Supplementing PageRank with git history (co-change frequency, bug history) and embedding similarity.
- **Runtime Learning:** Moving from deterministic retries to updating memory upon patch failure to continuously improve future prompts.
- **Semantic Contracts:** Upgrading validation from interface-level checks to strong semantic contracts (side effects, invariants, purity, thread safety).
- **Scalability Experiments:** Validating success rate degradation on frontier repositories (e.g., FastAPI, Django, NumPy).
- **Quantitative Profiling:** Taxonomizing failure rates vs context size and expanding evaluations across a broader spectrum of model sizes (e.g., 7B vs 14B).

---

## Repository Structure

```text
local-sage/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── .gitignore
├── local_sage/       # Core framework logic (agents, validation, memory)
├── examples/         # Example usage and development scripts
├── docs/             # Research paper, taxonomy, and methodology
├── results/          # Tabular datasets and logs
└── tests/            # Test harness for the agent capabilities
```

---

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/2005legend/SLM-Research-.git
cd SLM-Research
```

### 2. Create environment & Install
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### 3. Pull benchmark models
```bash
ollama pull qwen2.5-coder:7b
ollama pull deepseek-coder:6.7b
ollama pull llama3.1:8b
ollama pull qwen3.5:9b
```

---

## Citation

If you use this repository, cite both the codebase and the associated paper.

```bibtex
@misc{localsage2026,
  author       = {<AUTHOR_NAME>},
  title        = {local-sage: A Local Coding Agent Benchmark for Small Language Models},
  year         = {2026},
  howpublished = {GitHub repository},
  url          = {https://github.com/2005legend/SLM-Research-}
}
```

---

## Paper

- Draft paper: [`docs/paper/paper.md`](./docs/paper/paper.md)
- Benchmark protocol: [`docs/benchmark_protocol.md`](./docs/benchmark_protocol.md)
- Failure taxonomy: [`docs/failure_taxonomy.md`](./docs/failure_taxonomy.md)
- Reproducibility guide: [`docs/reproducibility.md`](./docs/reproducibility.md)
