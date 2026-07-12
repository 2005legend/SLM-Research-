# Reproducibility Guide

To ensure meaningful comparisons and reproducible results when executing the `local-sage` benchmark suite, please adhere to the following guidelines.

## 1. Environment and Hardware

When publishing your benchmark results, document your hardware and environment exactly as shown in the table below:

| Component | Value |
|---|---|
| OS | Windows (PowerShell) / Linux / macOS |
| Python | 3.10+ |
| Ollama | `<Version>` |
| CPU | `<CPU_NAME>` |
| GPU | `<GPU_NAME>` |
| VRAM | `<VRAM_GB>` |
| RAM | `<SYSTEM_RAM_GB>` |

## 2. Benchmark Execution

### Start the local assistant
Ensure your Ollama server is running in the background:
```bash
ollama serve
```

### Configure the target model
In `sage.toml` or directly in `run_harness_multi.py`, ensure the target model is specified exactly as pulled from Ollama:
```python
config.ollama_model = "llama3.1:8b"
```

### Run the benchmark suite
Execute the harness runner. The harness dynamically generates the test dummy fixtures (`dummy_multi_*.py`) to guarantee pristine environments before patching.
```bash
python run_harness_multi.py
```

## 3. Strict Controls
For valid, apples-to-apples comparisons:
- **Freeze the repository:** Use the same commit of the validation harness (`runner.py`, `patcher.py`) for all model benchmarks.
- **Identical Fixtures:** Do not manually edit the `dummy_multi` fixtures. Let the harness generate them automatically.
- **Consistent Retry Count:** Retries are hardcoded to `3` in `AtomicTask.max_retries`. Do not alter this between runs.
- **Scoped Validation:** Ensure `ValidationRunner` only lints the `changed_files` list, not the entire repository.

## 4. Exporting Results
The final results from Phase 1 testing have been aggregated into a standard tabular format:
- View results at: `results/tables/master_results.csv`
